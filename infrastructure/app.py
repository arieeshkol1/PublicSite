#!/usr/bin/env python3
import aws_cdk as cdk
from aws_cdk import Environment
from .network_stack import NetworkStack
from .storage_stack import StorageStack

app = cdk.App()

# Single, explicit env
env = Environment(account="991105135552", region="us-east-1")  # <- change region if needed

# Create VPC first
network = NetworkStack(app, "TSG-Network", env=env)   # must expose `self.vpc`

# Pass the VPC to StorageStack
storage = StorageStack(app, "TSG-Storage", vpc=network.vpc, env=env)

# Ensure synth order is stable (and cross-stack refs are fine)
storage.add_dependency(network)

app.synth()
