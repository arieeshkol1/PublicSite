import boto3, json

r53 = boto3.client('route53')

change_batch = {
    "Changes": [
        {
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": "slashmycloudbill.com",
                "Type": "A",
                "AliasTarget": {
                    "HostedZoneId": "Z2FDTNDATAQYW2",
                    "DNSName": "d13k71im98zj35.cloudfront.net",
                    "EvaluateTargetHealth": False
                }
            }
        },
        {
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": "slashmycloudbill.com",
                "Type": "AAAA",
                "AliasTarget": {
                    "HostedZoneId": "Z2FDTNDATAQYW2",
                    "DNSName": "d13k71im98zj35.cloudfront.net",
                    "EvaluateTargetHealth": False
                }
            }
        },
        {
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": "www.slashmycloudbill.com",
                "Type": "A",
                "AliasTarget": {
                    "HostedZoneId": "Z2FDTNDATAQYW2",
                    "DNSName": "d13k71im98zj35.cloudfront.net",
                    "EvaluateTargetHealth": False
                }
            }
        }
    ]
}

result = r53.change_resource_record_sets(
    HostedZoneId='Z08610352PUNQ7MUZTRVI',
    ChangeBatch=change_batch
)
print("DNS records created:", result['ChangeInfo']['Status'])
print("Change ID:", result['ChangeInfo']['Id'])
