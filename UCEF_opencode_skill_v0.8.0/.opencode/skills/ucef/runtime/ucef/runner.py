import json
import os
import shlex
import subprocess
import urllib.request


class CommandModelAdapter:
    def __init__(self, command, timeout_seconds=300):
        self.command = command
        self.timeout_seconds = timeout_seconds

    def generate(self, prompt):
        proc = subprocess.run(
            shlex.split(self.command), input=prompt, text=True,
            capture_output=True, timeout=self.timeout_seconds
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip())
        return proc.stdout


class OpenAICompatibleHTTPAdapter:
    def __init__(self, endpoint, model, api_key_env="UCEF_MODEL_API_KEY", timeout_seconds=300):
        self.endpoint = endpoint
        self.model = model
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def generate(self, prompt):
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.environ.get(self.api_key_env, '')}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


import json
import re


class WorkUnitRunner:
    def __init__(self, context_builder, validator, model=None):
        self.context_builder = context_builder
        self.validator = validator
        self.model = model

    def build_context(self, scenario, work_unit):
        return self.context_builder.build(scenario, work_unit)

    def run(self, scenario, work_unit):
        if self.model is None:
            raise RuntimeError("No model adapter configured")
        prompt = self.build_context(scenario, work_unit)
        text = self.model.generate(prompt)
        output = parse_model_json(text)
        return self.validator.ingest(output, scenario["scenario_id"], work_unit["work_unit_id"])


def parse_model_json(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if match:
        return json.loads(match.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("Model output does not contain a JSON object")
