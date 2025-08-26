from aws_cdk import (
    Stack,
)
from constructs import Construct

class IamCiStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # Intentionally empty – OIDC role is created via CloudFormation template in scripts/github-oidc-role.yaml
        # You can later migrate that into CDK if desired.