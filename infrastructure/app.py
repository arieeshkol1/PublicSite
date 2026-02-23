#!/usr/bin/env python3
import aws_cdk as cdk
from stack import Made4NetFortressStack

app = cdk.App()
Made4NetFortressStack(app, "Made4NetFortressStack",
    env=cdk.Environment(
        account='991105135552',
        region='us-east-1'
    ),
    description="Made4Net Fortress & Factory - OpsEx & Security POC"
)

app.synth()
