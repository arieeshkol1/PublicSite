# infrastructure/stacks/compute_stack.py
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_autoscaling as autoscaling,
    aws_iam as iam,
)
from constructs import Construct


class ComputeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, vpc: ec2.IVpc, buckets: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1) Security Group for ASG instances
        asg_sg = ec2.SecurityGroup(
            self, "AsgSg",
            vpc=vpc,
            description="Security group for ASG instances",
            allow_all_outbound=True,  # outbound egress allowed
        )

        # 2) Instance Role (SSM access is handy for debug/management)
        instance_role = iam.Role(
            self, "AsgInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="Role for ASG EC2 instances",
        )
        instance_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
        )

        # 3) Launch Template WITH the Security Group attached
        lt = ec2.LaunchTemplate(
            self, "AsgLt",
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            instance_type=ec2.InstanceType("c6a.2xlarge"),
            security_group=asg_sg,           # <-- CRITICAL: makes ASG IConnectable
            role=instance_role,
            detailed_monitoring=True,
            user_data=ec2.UserData.for_linux(),  # add your bootstrap if needed
        )

        # 4) Auto Scaling Group using the Launch Template
        asg_grp = autoscaling.AutoScalingGroup(
            self, "AsgGrp",
            vpc=vpc,
            min_capacity=1,
            max_capacity=4,
            desired_capacity=1,
            launch_template=lt,  # use LT that already carries the SG
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # NOTE: This would be redundant with allow_all_outbound=True, so leave it commented.
        # asg_grp.connections.allow_to_any_ipv4(ec2.Port.all_traffic(), "Egress for updates/artifacts")
