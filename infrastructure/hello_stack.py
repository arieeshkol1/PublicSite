from aws_cdk import Stack
from constructs import Construct

class HelloStack(Stack):
    def __init__(self, scope: Construct, cid: str, **kwargs):
        super().__init__(scope, cid, **kwargs)
        # Intentionally no resources; safe to synth/deploy.
        # This will create an empty CloudFormation stack, which is free.
