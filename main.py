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

# Function to speak the response


def speak_response(text):
    engine = pyttsx3.init()

    # List available voices
    voices = engine.getProperty('voices')

    # Set to the first English voice found
    for voice in voices:
        if "english" in voice.name.lower():
            engine.setProperty('voice', voice.id)
            break

    # Adjust speech rate (words per minute)
    engine.setProperty('rate', 175)

    # Adjust volume (0.0 to 1.0)
    engine.setProperty('volume', 0.8)

    engine.say(text)
    engine.runAndWait()

# Main loop
# some comments and changes try to make it more efficient


def main():
    while True:
        command = recognize_speech()
        if command:
            if "hello" in command:
                # Remove the word 'Jarvis' before processing
                clean_command = command.replace("hello", "").strip()
                print("Processing command:", clean_command)

                if "turn on" in clean_command or "turn off" in clean_command:
                    # Replace with your actual device ID
                    device_id = os.getenv('TUYA_DEVICE_ID')
                    tuya_response = control_tuya_device(
                        device_id, clean_command)
                    print(tuya_response)
                    speak_response(tuya_response)  # Speak the Tuya response
                else:
                    # Adjust max_tokens as needed
                    gpt_response = get_gpt_response(
                        clean_command, max_tokens=50)
                    print("GPT Response:", gpt_response)
                    speak_response(gpt_response)  # Speak the GPT response


if __name__ == "__main__":
    main()
