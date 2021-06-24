This lambda was written to handle the gap that exists between ECS Blue/Green Deploys and Application Auto Scaling
As it stands currently, when leveraging Blue Green Deployement scheme within ECS, the deployment will not update the managed Application Auto Scaling Policy. 

Current advice is to suspend the Auto-Scaling Policy prior to deployment, and then re-create it after deployment. 

This is.....fine but ultimately is a bit involved, so, I automated it. 

The TL;DR is as such:
    - assuming 4 pieces of constant information this script will run as both a post-install hook, and a cloud watch event rule 
    - the logic checks the active policy against the live target group 
    - if there's a match, the lambda will do nothing
    - if the resource label for the policy does not match the live target group, it will replace the auto-scaling policy with one that is correct

This ensures that application auto scaling won't break on every other deploy. 
By running it twice via cw event rule AND as a deploy hook it achieves some level of idempotency 

feel free to take this and run with it.

the four pieces of info you need are:

    - LoadBalancer Name 
    - ECS Cluster ARN
    - ECS Service ARN 
    - Resource Name (from the Scaling Policy)

The event passed into the lambda is different depending on whether it is triggered by the cloudwatch source, or, the hook. 
To account for that I have the lambda event handler hand off the entire event to a function that determines the trigger source.
I did this by looking for specific keys in the event that it passed in, and then depending on the keys that are found, construct a dictionary with the constants we need for the API calls down the line. 
This avoids needing to hardcode any resources as strings 


So, for example, if triggered as a hook the DeploymentId and LifecycleEventHookExecutionId are in the event, and so they are preserved for later use after the policy has been updated. 
The rest of the logic however is pretty much as follows:
    - get the Deployment Group Info
    - pull out the bits you need for the API calls you're going to have to make. 
    - find the active target group by pulling out the active target group from the forwarding config
    - look for a match on the targetgroup from the forwarding config
    - describe the current scaling policy and pull the active policy name and resource label 
    - construct a temporary resource label using the target group that we identified as active from the forwarding config
    - compare the resource labels, if they match do nothing, exit. if they do not match, put the new policy in place using the new resource label we constructed.  

That flow is the same regardless of trigger source, and in my tests has worked pretty well, including being run immediately after a stop and rollback from the cloudwatch trigger. 
At this point, even if there were a temporary API call failure, having it execute as a hook, and as a match on a successful, stopped, or failed state basically supplies some redundancy. 

there's a terraform file you can use to spin up an ECS cluster and service with Blue / Green setup
for that file you'll need to modify it for use within your account / vpc / subnets
for the container image that will comprise our task you can just set it up to use nginx 


