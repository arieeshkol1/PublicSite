from aws_cdk import App, Environment
from stacks.network_stack import NetworkStack
from stacks.storage_stack import StorageStack
from stacks.compute_stack import ComputeStack
from stacks.iam_ci_stack import IamCiStack

app = App()

env = Environment(account="991105135552", region="us-east-1")  # <— pin here

network = NetworkStack(app, "TSG-Network", env=env)
storage = StorageStack(app, "TSG-Storage", env=env)
compute = ComputeStack(app, "TSG-Compute", vpc=network.vpc, buckets=storage.buckets, env=env)
iam_ci = IamCiStack(app, "TSG-IamCi", env=env)

app.synth()
