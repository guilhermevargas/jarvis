import speech_recognition as sr
from openai import OpenAI
from tuya_connector import TuyaOpenAPI
import pyttsx3
import ssl
import certifi
import httpx
import os
from dotenv import load_dotenv
import re
import time
from queue import Queue
from threading import Thread
import threading
import queue

# Load environment variables from .env file
load_dotenv()

# Add this near the top of your file, after the imports
ssl_context = ssl.create_default_context(cafile=certifi.where())
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Configuration for Oimport openai

client = OpenAI(
    api_key=os.getenv('OPENAI_API_KEY'),
    http_client=httpx.Client(verify=ssl_context)
)

# Tuya API Initialization
# Use the appropriate endpoint for your region
ENDPOINT = os.getenv('TUYA_ENDPOINT')
ACCESS_ID = os.getenv('TUYA_ACCESS_ID')  # Replace with your Tuya Access ID
ACCESS_KEY = os.getenv('TUYA_ACCESS_KEY')  # Replace with your Tuya Access Key
tuya_api = TuyaOpenAPI(ENDPOINT, ACCESS_ID, ACCESS_KEY)
tuya_api.connect()

conversation_active = False
conversation_history = []
command_queue = Queue()
is_speaking = False
interrupt_queue = queue.Queue()
stop_speaking = threading.Event()

# Function to recognize speech


def recognize_speech():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening...")
        audio = recognizer.listen(source)
        try:
            command = recognizer.recognize_google(audio)
            print(f"Recognized: {command}")
            return command
        except sr.UnknownValueError:
            print("Sorry, I could not understand that.")
            return None
        except sr.RequestError as e:
            print("Could not request results; {0}".format(e))
            return None

# Function to communicate with OpenAI GPT


def get_gpt_response(prompt, max_tokens=100):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens
    )
    return response.choices[0].message.content.strip()

# Function to control Tuya devices


def control_tuya_device(device_id, command):
    commands = {
        "turn on lights": {"commands": [{"code": "switch_led", "value": True}]},
        "turn off lights": {"commands": [{"code": "switch_led", "value": False}]}
    }

    command_lower = command.lower()
    if command_lower in commands:
        try:
            response = tuya_api.post(
                f'/v1.0/iot-03/devices/{device_id}/commands', commands[command_lower])
            if response['success']:
                return f"Device {command_lower} successfully"
            else:
                return f"Failed to {command_lower} the device"
        except Exception as e:
            return f"Error controlling device: {str(e)}"
    else:
        return "I didn't understand the command."

# Modify the speak_response function


def speak_response(text):
    global is_speaking
    is_speaking = True
    engine = pyttsx3.init()

    def on_word(name, location, length):
        if stop_speaking.is_set():
            engine.stop()

    engine.connect('started-word', on_word)
    engine.say(text)
    engine.runAndWait()

    is_speaking = False
    stop_speaking.clear()

# Modify the recognize_speech_thread function


def recognize_speech_thread():
    global is_speaking
    while True:
        if not is_speaking:
            command = recognize_speech()
            if command:
                command_queue.put(command)
        else:
            # Check for interrupt commands
            interrupt_command = recognize_speech(timeout=1)
            if interrupt_command and interrupt_command.lower() in ["stop", "enough", "ok"]:
                interrupt_queue.put(interrupt_command)
                stop_speaking.set()

# Modify the main function


def main():
    global conversation_active, conversation_history, is_speaking

    # Start the speech recognition thread
    speech_thread = Thread(target=recognize_speech_thread, daemon=True)
    speech_thread.start()

    while True:
        if not command_queue.empty() and not is_speaking:
            command = command_queue.get()

            # Process the command
            if not conversation_active:
                print("Conversation not active. Checking for 'hello'...")
                if "hello" in command.lower():
                    conversation_active = True
                    conversation_history = []
                    clean_command = command.replace("hello", "").strip()
                    speak_response("Hello! How can I help you today?")
                else:
                    print("Conversation not active. Say 'hello' to start.")
                    continue
            else:
                print("Conversation active. Processing command...")
                clean_command = command

            print("Processing command:", clean_command)
            conversation_history.append(f"User: {clean_command}")

            if "turn on" in clean_command or "turn off" in clean_command:
                device_id = os.getenv('TUYA_DEVICE_ID')
                tuya_response = control_tuya_device(device_id, clean_command)
                print(tuya_response)
                speak_response(tuya_response)
                conversation_history.append(f"Assistant: {tuya_response}")
            else:
                full_prompt = "\n".join(
                    conversation_history[-5:]) + f"\nAssistant: "
                gpt_response = get_gpt_response(full_prompt, max_tokens=100)
                print("GPT Response:", gpt_response)

                speak_response(gpt_response)

                if not interrupt_queue.empty():
                    interrupt_command = interrupt_queue.get()
                    print(f"Interrupted with: {interrupt_command}")
                    conversation_history.append(
                        f"Assistant: {gpt_response} (interrupted)")
                else:
                    conversation_history.append(f"Assistant: {gpt_response}")

            # Reset the last interaction time
            last_interaction_time = time.time()

        elif conversation_active and (time.time() - last_interaction_time) > 60 and not is_speaking:
            # End conversation after 60 seconds of inactivity
            conversation_active = False
            speak_response(
                "The conversation has ended due to inactivity. Say 'hello' to start a new conversation.")
            conversation_history = []
        else:
            time.sleep(0.1)  # Short sleep to prevent busy-waiting


if __name__ == "__main__":
    main()
