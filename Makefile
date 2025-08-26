SHELL := /bin/bash
PY := python3

.PHONY: venv install bootstrap deploy destroy synth

venv:
	$(PY) -m venv .venv && source .venv/bin/activate && pip install -r infrastructure/requirements.txt

install:
	pip install -r infrastructure/requirements.txt

bootstrap:
	cd infrastructure && cdk bootstrap

deploy:
	cd infrastructure && cdk deploy --all --require-approval never

destroy:
	cd infrastructure && cdk destroy --all --force

synth:
	cd infrastructure && cdk synth