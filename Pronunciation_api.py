from fastapi import FastAPI, File, UploadFile, Form, Header
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import HTTPException
from typing import Optional
import azure.cognitiveservices.speech as speechsdk
import uvicorn
import time
import asyncio
from multiprocessing import Process
import json
import aiohttp


app = FastAPI()

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
    speech_key: str = Header(...),
    service_region: str = Header(...),
    url: str = Form(...),
    reference_text: Optional[str] = Form(default=""),
    grading_system: Optional[str] = Form(default="HundredMark"),
    grantularity: Optional[str] = Form(default="Phoneme"),
    dimension: Optional[str] = Form(default="Comprehensive"),
    enable_miscue: Optional[bool] = Form(default=False),
    enable_prosody: Optional[bool] = Form(default=True),
    phoneme_alphabet: Optional[str] = Form(default="IPA"),
):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
    target_filename = url.split("/")[-1]
    import uuid

    # Append a random UUID to the target filename to avoid duplicates
    target_filename = f"{uuid.uuid4()}_{target_filename}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                error_message = await response.text()
                # Raise an HTTPException with the status code and error message
                raise HTTPException(status_code=response.status, detail=error_message)
            with open(target_filename, 'wb') as fd:
                while True:
                    chunk = await response.content.readany()
                    if not chunk:
                        break
                    fd.write(chunk)


    config_json = {
        "GradingSystem": grading_system,
        "Granularity": grantularity,
        "Dimension": dimension,
        "ScenarioId": "",  # "" is the default scenario or ask product team for a customized one
        "EnableMiscue": enable_miscue,
        "EnableProsodyAssessment": enable_prosody,
        "NBestPhonemeCount": 0,  # > 0 to enable "spoken phoneme" mode, 0 to disable
        "PhonemeAlphabet": phoneme_alphabet,
    }

    queue = Queue()
    checker = PronunciationCheck(target_filename, reference_text, config_json, speech_key, service_region, queue=queue)

    p = Process(target=checker.speech_recognize_continuous_from_file)
    p.start()
    return StreamingResponse(stream_output(queue), media_type="text/event-stream")


async def stream_output(queue):
    while True:
        if not queue.empty():
            data = queue.get()  # Retrieve data from the queue
            #if received data is '[DONE]', then break the loop
            if data == '[DONE]':
                # Send the string '[DONE]' to the client, no Json format
                yield b'data: ' + b'[DONE]' + b'\n\n'
                break
            yield b'data: ' + json.dumps(data).encode() + b'\n\n'
        await asyncio.sleep(0.9)


from multiprocessing import Process, Queue

class PronunciationCheck:
    def __init__(self, filename, reference_text, config_json, speech_key, service_region, queue):
        self.filename = filename
        self.reference_text = reference_text
        self.config_json = config_json
        self.speech_key = speech_key
        self.service_region = service_region
        self.queue = queue

    def on_recognized(self, evt):
        self.queue.put(json.loads(evt.result.json))  # Send data to the queue
           

    def speech_recognize_continuous_from_file(self):

        # Create a compressed format for MP3
        compressed_format = speechsdk.audio.AudioStreamFormat(compressed_stream_format=speechsdk.AudioStreamContainerFormat.ANY)
        
        # Create the callback and stream
        callback = BinaryFileReaderCallback(self.filename)
        stream = speechsdk.audio.PullAudioInputStream(stream_format=compressed_format, pull_stream_callback=callback)

        speech_config = speechsdk.SpeechConfig(subscription=self.speech_key, region=self.service_region)
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
        # Close the file
        callback.close()
        # Delete the file
        import os
        os.remove(self.filename)
        
        # Close the queue
        self.queue.put('[DONE]')

    def get_output_obj(self):
        return self.output_obj


if __name__ == "__main__":
    uvicorn.run("Pronunciation_api:app", host="0.0.0.0", port=8080)
