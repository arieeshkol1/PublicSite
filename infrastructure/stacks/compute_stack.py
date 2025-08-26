from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_autoscaling as asg,
    Duration,
)
from constructs import Construct

class ComputeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, vpc: ec2.IVpc, buckets: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Instance profile for EC2 with SSM and S3 access
        role = iam.Role(self, "Ec2Role",
                        assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"))
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"))
        # Narrow S3 permissions in production; sandbox allows full access to the three buckets
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess"))

        lt = ec2.LaunchTemplate(
            self, "LaunchTemplate",
            instance_type=ec2.InstanceType("c6a.2xlarge"),  # 8 vCPU / 16 GiB
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            role=role,
            detailed_monitoring=True,
        )

        asg_grp = asg.AutoScalingGroup(
            self, "TileWorkersAsg",
            vpc=vpc,
            min_capacity=0,
            max_capacity=10,
            desired_capacity=1,
            launch_template=lt,
            signals=asg.Signals.wait_for_count(1, timeout=Duration.minutes(15)),
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # Allow outbound only; inbound via SSM Session Manager (no SSH keys)
        asg_grp.connections.allow_to_any_ipv4(ec2.Port.all_traffic(), "Egress for updates/artifacts")