These pair of lambdas are written to do the following:

    - One kicks off vulns scans for every image in every repo in the account/region it runs in
    - The second one polls the results for all the scans run and dumps them in SQS 

From SQS you can then easily ingest into a log aggregator like splunk, or leverage SNS to ship the results off to your email by chaging the ship_results function 
see here for more info on the calls used:

 - https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ecr.html#client
 - https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sqs.html#SQS.Client.send_message


you just need to deploy, add the service specific perms, and then set a cron rule to kick them off 
