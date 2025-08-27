#!/usr/bin/env python3
import aws_cdk as cdk
from aws_cdk import Environment
from .stack import ServerlessJp2Stack

app = cdk.App()

account = app.node.try_get_context("account") or "991105135552"
region = app.node.try_get_context("region") or "us-east-1"
prefix = app.node.try_get_context("stack_prefix") or "TSG"

env = Environment(account=account, region=region)

ServerlessJp2Stack(app, f"{prefix}-ServerlessJp2", env=env)

app.synth()
