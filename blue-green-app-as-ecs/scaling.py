import boto3
import json

code = boto3.client('codedeploy', region_name='us-east-2')
appas = boto3.client('application-autoscaling', region_name='us-east-2')
ecs = boto3.client('ecs', region_name='us-east-2')
elbv2 = boto3.client('elbv2', region_name='us-east-2')


def lambda_handler(event, context):
    trigger_source(event)
    print('Done')
    return {
        'statusCode': 200,
        'body': json.dumps('Completed')
    }


def trigger_source(event):
    print(event)
    if "LifecycleEventHookExecutionId" in event:
        payload = {}
        lifecycleExecId = event['LifecycleEventHookExecutionId']
        deployId = event['DeploymentId']
        payload.update(deployId=deployId, lifecycle_hook=lifecycleExecId)
        deploy = get_deploy(deployId)
        app_n = deploy['deploymentInfo']['applicationName']
        depg_n = deploy['deploymentInfo']['deploymentGroupName']
        deploy_info = get_deploy_group(app_n, depg_n)
        clstr = deploy_info['deploymentGroupInfo']['ecsServices'][0]['clusterName']
        svc = deploy_info['deploymentGroupInfo']['ecsServices'][0]['serviceName']
        tgs = deploy_info['deploymentGroupInfo']['loadBalancerInfo']['targetGroupPairInfoList'][0]['targetGroups']
        lstnrs = []
        p_lstnr = deploy_info['deploymentGroupInfo']['loadBalancerInfo']['targetGroupPairInfoList'][0]['prodTrafficRoute']['listenerArns'][0]
        t_lstnr = deploy_info['deploymentGroupInfo']['loadBalancerInfo']['targetGroupPairInfoList'][0]['testTrafficRoute']['listenerArns'][0]
        lstnrs.append(p_lstnr)
        lstnrs.append(t_lstnr)  
        payload.update(clstr=clstr, svc=svc, tgs=tgs, lstnrs=lstnrs)
        main(payload)
    elif "detail" in event:
        payload = {}
        app_n = event['detail']['application']
        depg_n = event['detail']['deploymentGroup']
        deploy_info = get_deploy_group(app_n, depg_n)
        clstr = deploy_info['deploymentGroupInfo']['ecsServices'][0]['clusterName']
        svc = deploy_info['deploymentGroupInfo']['ecsServices'][0]['serviceName']
        tgs = deploy_info['deploymentGroupInfo']['loadBalancerInfo']['targetGroupPairInfoList'][0]['targetGroups']
        lstnrs = []
        p_lstnr = deploy_info['deploymentGroupInfo']['loadBalancerInfo']['targetGroupPairInfoList'][0]['prodTrafficRoute']['listenerArns'][0]
        t_lstnr = deploy_info['deploymentGroupInfo']['loadBalancerInfo']['targetGroupPairInfoList'][0]['testTrafficRoute']['listenerArns'][0]
        lstnrs.append(p_lstnr)
        lstnrs.append(t_lstnr)        
        payload.update(clstr=clstr, svc=svc, tgs=tgs, lstnrs=lstnrs)
        main(payload)
    else:
        print("Trigger Source undefined")
        exit


def main(payload):
    clstr = payload['clstr']
    svc = payload['svc']
    tgs = []
    parse = []
    lstnrs = payload['lstnrs']
    for i in payload['tgs']:
        tgs.append(i['name'])
    active_tg = find_active_tg(lstnrs,tgs)
    res_id = f'service/{clstr}/{svc}'
    current_policy= desc_policies(res_id)
    policy_name = current_policy['ScalingPolicies'][0]['PolicyName']
    current_res_label = current_policy['ScalingPolicies'][0]['TargetTrackingScalingPolicyConfiguration']['PredefinedMetricSpecification']['ResourceLabel']
    mod_res_label = current_res_label.split('/', 4)
    mod_res_label[4] = active_tg
    res_label = '/'.join(mod_res_label)
    print('================================================================')
    print(f'the current resource label is: {current_res_label}')
    print('================================================================')
    print(f'the proposed resource label is: {res_label}')
    print('================================================================')
    if 'lifecycle_hook' in payload.keys():
        print('invoked as Code Deploy Hook')
        deployID = payload['deployId']
        lifecycle_hook = payload['lifecycle_hook']
        if res_label != current_res_label:
            print('================================================================')
            print("resource labels do not match, setting new policy with the new label")
            policy = put_policy(policy_name, res_id, res_label)
            print('================================================================')
            print(f'updated policy is: {policy}')
            print('Policy updated successfully')
            print('================================================================')
            print('setting lifecycle hook status')
            print('================================================================')
            status = lifecycle_hook_put(policy, deployID, lifecycle_hook)
            exit
        else:
            print('================================================================')
            print('policy currently has active tg in place, nothing to do')
            print('================================================================')
            status = lifecycle_hook_put(policy, deployID, lifecycle_hook)
            exit
    else:
        print('invoked as Cloudwatch rule event match')
        if res_label != current_res_label:
            print('================================================================')
            print("resource labels do not match, setting new policy with the new label")
            policy = put_policy(policy_name, res_id, res_label)
            print('================================================================')
            print(f'updated policy is: {policy}')
            print('================================================================')
            print('Policy updated successfully')
            exit
        else:
            print('================================================================')
            print('policy currently has active tg in place, nothing to do')
            print('================================================================')
            exit


def get_deploy_group(app_n, depg_n):
    resp = code.get_deployment_group(
        applicationName=app_n,
        deploymentGroupName=depg_n
    )
    return resp


def get_deploy(deployId):
    resp = code.get_deployment(
        deploymentId=deployId
    )
    return resp


def desc_policies(res_id):
    resp = appas.describe_scaling_policies(
        ServiceNamespace='ecs',
        ResourceId=res_id,
        ScalableDimension='ecs:service:DesiredCount'
    )
    policy = resp
    return policy


def find_active_tg(lstnrs, tgs):
    active_tg = ''
    parse = []
    for i in lstnrs:
        resp = elbv2.describe_rules(
            ListenerArn=i,
        )
        tg = resp['Rules'][0]['Actions'][0]['ForwardConfig']['TargetGroups']
        for i in tg:
            parse.append(tg[0]['TargetGroupArn'])
    tg_parse = parser(parse)
    check = tg_parse['targetgroup'].split('/', 1)
    for i in tgs:
        if check[0] == i:
            active_tg = tg_parse['targetgroup']
    return active_tg


def parser(parse):
    tg_1 = None
    tg_2 = None
    add = {}
    for i in parse:
        elements = i.split(':', 5)
        result = {
            'arn': elements[1],
            'partition': elements[2],
            'service': elements[3],
            'region_name': elements[4],
            'resource': elements[5]
        }
        part = result['resource'].split('/', 1)
        i = tuple(part)
        if tg_1 is None:
            tg_1 = i
        else:
            tg_2 = i
    if tg_1[1] == tg_2[1]:
        add.update({i})
    else:
        print('expected to find exactly one target group and instead found two')
    return add


def put_policy(policy_name, res_id, res_label):
    resp = appas.put_scaling_policy(
        PolicyName=policy_name,
        ServiceNamespace='ecs',
        ResourceId=res_id,
        ScalableDimension='ecs:service:DesiredCount',
        PolicyType='TargetTrackingScaling',
        TargetTrackingScalingPolicyConfiguration={
            'TargetValue': 10,
            'PredefinedMetricSpecification': {
                'PredefinedMetricType': 'ALBRequestCountPerTarget',
                'ResourceLabel': res_label
            },
            'ScaleOutCooldown': 60,
            'ScaleInCooldown': 60,
            'DisableScaleIn': False
            }
    )
    return resp


def lifecycle_hook_put(policy, deployId, lifecycleExecId):
    if policy['ResponseMetadata']['HTTPStatusCode'] == 200:
        resp = code.put_lifecycle_event_hook_execution_status(
            deploymentId=deployId,
            lifecycleEventHookExecutionId=lifecycleExecId,
            status='Succeeded'
        )
    else:
        resp = code.put_lifecycle_event_hook_execution_status(
            deploymentId=deployId,
            lifecycleEventHookExecutionId=lifecycleExecId,
            status='Failed'
        )
    return resp
