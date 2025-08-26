#!/usr/bin/env python3
import os
import aws_cdk as cdk
from stacks.network_stack import NetworkStack
from stacks.storage_stack import StorageStack
from stacks.compute_stack import ComputeStack
from stacks.iam_ci_stack import IamCiStack

app = cdk.App()

env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"),
)

network = NetworkStack(app, "TSG-Network", env=env)
storage = StorageStack(app, "TSG-Storage", vpc=network.vpc, env=env)
compute = ComputeStack(app, "TSG-Compute", vpc=network.vpc, buckets=storage.buckets, env=env)
iam_ci = IamCiStack(app, "TSG-IamCi", env=env)

app.synth()