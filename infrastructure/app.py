#!/usr/bin/env python3
import aws_cdk as cdk
from aws_cdk import Environment
from .hello_stack import HelloStack

app = cdk.App()

# Single-account, single-region environment
env = Environment(account="991105135552", region="us-east-1")

# Minimal, risk-free stack (no resources created)
HelloStack(app, "TSG-Hello", env=env)

app.synth()
