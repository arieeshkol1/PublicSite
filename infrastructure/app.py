import os
from aws_cdk import App, Environment
from stack import ServerlessJp2Stack

app = App()

ServerlessJp2Stack(
    app, "ServerlessJp2",
    env=Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION"),
    ),
)

app.synth()
