#!/usr/bin/env python3
"""
TAG Video Systems - Serverless Video Probe Monitoring System
CDK Application Entry Point
"""
import os
from aws_cdk import App, Environment
from stack import TagVideoProbeStack

app = App()

# Get AWS account and region from environment or use defaults
account = os.environ.get("AWS_ACCOUNT_ID", "991105135552")
region = os.environ.get("AWS_REGION", "us-east-1")

env = Environment(account=account, region=region)

TagVideoProbeStack(
    app,
    "TagVideoProbeStack",
    env=env,
    description="TAG Video Systems - Serverless Video Probe Monitoring POC"
)

app.synth()
