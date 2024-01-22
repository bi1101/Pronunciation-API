from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from typing import Optional
import azure.cognitiveservices.speech as speechsdk
import uvicorn
import time
import asyncio
import threading
import json
import aiohttp


app = FastAPI()

speech_key, service_region = "ad5c38b8edf14fc382ac17533393df30", "eastus"

class BinaryFileReaderCallback(speechsdk.audio.PullAudioInputStreamCallback):
    def __init__(self, filename: str):
        super().__init__()
        self._file_h = open(filename, "rb")

    def read(self, buffer: memoryview) -> int:
        size = buffer.nbytes
        frames = self._file_h.read(size)
        buffer[:len(frames)] = frames
        return len(frames)

    def close(self) -> None:
        self._file_h.close()


@app.post("/")
async def pronunciation_check(
    url: str = Form(...),
    reference_text: Optional[str] = Form(default=""),
    grading_system: Optional[str] = Form(default="HundredMark"),
    grantularity: Optional[str] = Form(default="Phoneme"),
    dimension: Optional[str] = Form(default="Comprehensive"),
    enable_miscue: Optional[bool] = Form(default=False),
    enable_prosody: Optional[bool] = Form(default=True),
):
    target_filename = url.split("/")[-1]
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                return {"message": "couldn't get audio from URL"}
            with open(target_filename, 'wb') as fd:
                while True:
                    chunk = await response.content.readany()
                    if not chunk:
                        break
                    fd.write(chunk)
            #while True:
            #    chunk = await file.read(1024)
            #    if not chunk:
            #        break
            #    fd.write(chunk)


    config_json = {
        "GradingSystem": grading_system,
        "Granularity": grantularity,
        "Dimension": dimension,
        "ScenarioId": "",  # "" is the default scenario or ask product team for a customized one
        "EnableMiscue": enable_miscue,
        "EnableProsodyAssessment": enable_prosody,
        "NBestPhonemeCount": 0,  # > 0 to enable "spoken phoneme" mode, 0 to disable
    }

    checker = PunctuationCheck(target_filename, reference_text, config_json)

    t = threading.Thread(target=checker.speech_recognize_continuous_from_file)
    t.start()
    return StreamingResponse(stream_output(t, checker), media_type="text/event-stream")


async def stream_output(thread, checker):
    while thread.is_alive():
        yield b'data: ' + json.dumps(checker.get_output_obj()).encode() + b'\n\n'
        await asyncio.sleep(0.9)


class PunctuationCheck:
    def __init__(self, filename, reference_text, config_json):
        self.filename = filename
        self.reference_text = reference_text
        self.config_json = config_json
        self.output_obj = {}

    def on_recognized(self, evt):
        #pronunciation_result = speechsdk.PronunciationAssessmentResult(evt.result)
        self.output_obj = json.loads(evt.result.json)

    def speech_recognize_continuous_from_file(self):

        # Create a compressed format for MP3
        compressed_format = speechsdk.audio.AudioStreamFormat(compressed_stream_format=speechsdk.AudioStreamContainerFormat.ANY)
        
        # Create the callback and stream
        callback = BinaryFileReaderCallback(self.filename)
        stream = speechsdk.audio.PullAudioInputStream(stream_format=compressed_format, pull_stream_callback=callback)

        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
        #audio_config = speechsdk.audio.AudioConfig(filename=self.filename)
        audio_config = speechsdk.audio.AudioConfig(stream=stream)

        speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config, language="en-US")

        pronunciation_config = speechsdk.PronunciationAssessmentConfig(json_string=json.dumps(self.config_json))
        pronunciation_config.reference_text = self.reference_text

        pronunciation_config.apply_to(speech_recognizer)

        done = False

        def stop_cb(evt: speechsdk.SessionEventArgs):
            nonlocal done
            done = True

        speech_recognizer.recognized.connect(self.on_recognized)
        speech_recognizer.session_stopped.connect(stop_cb)
        speech_recognizer.canceled.connect(stop_cb)

        # Start continuous speech recognition
        speech_recognizer.start_continuous_recognition()
        while not done:
            time.sleep(.5)

        speech_recognizer.stop_continuous_recognition()

    def get_output_obj(self):
        return self.output_obj


if __name__ == "__main__":
    uvicorn.run("code:app", host="0.0.0.0", port=8080)
