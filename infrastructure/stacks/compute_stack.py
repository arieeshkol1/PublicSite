diff --git a/infrastructure/stacks/compute_stack.py b/infrastructure/stacks/compute_stack.py
index 1111111..2222222 100644
--- a/infrastructure/stacks/compute_stack.py
+++ b/infrastructure/stacks/compute_stack.py
@@ -1,8 +1,10 @@
 from aws_cdk import (
     Stack,
-    aws_ec2 as ec2,
-    aws_autoscaling as autoscaling,
+    aws_ec2 as ec2,
+    aws_autoscaling as autoscaling,
 )
 from constructs import Construct

 class ComputeStack(Stack):
     def __init__(self, scope: Construct, construct_id: str, *, vpc: ec2.IVpc, buckets: dict, **kwargs) -> None:
         super().__init__(scope, construct_id, **kwargs)
 
-        # ... existing code ...
+        # --- 1) Security Group for ASG instances ---
+        asg_sg = ec2.SecurityGroup(
+            self, "AsgSg",
+            vpc=vpc,
+            description="Security group for ASG instances",
+            allow_all_outbound=True,  # outbound egress permitted by default
+        )
+
+        # --- 2) Launch Template WITH the Security Group attached ---
+        lt = ec2.LaunchTemplate(
+            self, "AsgLt",
+            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
+            instance_type=ec2.InstanceType("c6a.2xlarge"),
+            security_group=asg_sg,            # <-- CRITICAL: makes ASG IConnectable
+            detailed_monitoring=True,
+            user_data=ec2.UserData.for_linux(),  # add your bootstrap if you have one
+        )
 
-        asg_grp = autoscaling.AutoScalingGroup(
+        # --- 3) Auto Scaling Group using the Launch Template ---
+        asg_grp = autoscaling.AutoScalingGroup(
             self, "AsgGrp",
             vpc=vpc,
-            min_capacity=1,
-            max_capacity=4,
-            desired_capacity=1,
-            instance_type=ec2.InstanceType("c6a.2xlarge"),
-            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
-            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
+            min_capacity=1,
+            max_capacity=4,
+            desired_capacity=1,
+            launch_template=lt,  # use LT that already carries the SG
+            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
         )
 
-        # This line fails without an SG on the LT/ASG. Safe now, but redundant.
-        asg_grp.connections.allow_to_any_ipv4(ec2.Port.all_traffic(), "Egress for updates/artifacts")
+        # Optional: now valid but redundant thanks to allow_all_outbound=True
+        # asg_grp.connections.allow_to_any_ipv4(ec2.Port.all_traffic(), "Egress for updates/artifacts")
