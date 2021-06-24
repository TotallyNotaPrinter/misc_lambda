provider "aws" {
  version = "~> 2.56"
}

data "aws_region" "current" {}
data "aws_vpc" "this" {}

data "aws_subnet_ids" "compute_subnet" {
  vpc_id = data.aws_vpc.this.id
}

data "aws_subnet" "this" {
  for_each = data.aws_subnet_ids.compute_subnet.ids
  id       = each.value
}

locals {
  azs = [for s in data.aws_subnet.this: s.availability_zone]
  subnetsByAz = [for az in local.azs: [for s in data.aws_subnet.this: s.id if s.availability_zone == az]]
  subnetIdsToUse = [for sba in local.subnetsByAz: sba[0]]
}

resource "aws_ecs_cluster" "this" {
  name               = "autoscaling-demo"
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_security_group" "alb_sg" {
  name   = "autoscaling-demo-alb-sg"
  vpc_id = data.aws_vpc.this.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group_rule" "sg_alb_rule_1" {
  type              = "ingress"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.alb_sg.id
}

resource "aws_security_group_rule" "sg_alb_rule_3" {
  type              = "ingress"
  from_port         = 2049
  to_port           = 2049
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.ecs_sg.id
}

resource "aws_security_group_rule" "sg_alb_rule_4" {
  type              = "ingress"
  from_port         = 8090
  to_port           = 8090
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.alb_sg.id
}

#---------------------------------------------
resource "aws_security_group" "ecs_sg" {
  name   = "autoscaling-demo-ecs-sg"
  vpc_id = data.aws_vpc.this.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group_rule" "sg_ecs_rule_1" {
  type              = "ingress"
  from_port         = 0
  to_port           = 0
  protocol          = "all"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.ecs_sg.id
}

# =======================================================================================
# TASKS
# =======================================================================================
resource "aws_ecs_task_definition" "this_task_definition" {
  family                   = "autoscaling-demo-hello-world"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn = aws_iam_role.hello-world-execution-role.arn

  container_definitions = jsonencode([
    {
      "cpu" : 256,
      "memory" : 512,
      "image" : "nginxdemos/hello",
      "name" : "hello-world",
      "networkMode" : "awsvpc",
      "portMappings" : [
        {
          "hostPort" : 80,
          "containerPort" : 80
        }
      ],
      "LogConfiguration" : {
        "LogDriver" : "awslogs",
        "Options" : {
          "awslogs-region" : data.aws_region.current.name,
          "awslogs-group" : aws_cloudwatch_log_group.fargate_containers_logs.name,
          "awslogs-stream-prefix" : "autoscaling-demo-hello-world"
        }
      }
    }
  ])

  # We register a new taskDefinition in python, so don't want to change in place here
  lifecycle {
    ignore_changes = [cpu, memory, container_definitions]
  }
}

resource "aws_iam_role" "hello-world-execution-role" {
  assume_role_policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [{
      "Sid": "",
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "hello-world-AmazonECSTaskExecutionRolePolicy" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
  role       = aws_iam_role.hello-world-execution-role.name
}

# =======================================================================================
# ALB
# =======================================================================================
resource "aws_lb" "this_alb" {
  name               = "autoscaling-demo"
  subnets            = local.subnetIdsToUse
  security_groups    = [aws_security_group.alb_sg.id]
  internal           = true
  load_balancer_type = "application"
}

resource "aws_lb_target_group" "blue_tg" {
  protocol                      = "HTTP"
  deregistration_delay          = 60
  port                          = 80
  vpc_id                        = data.aws_vpc.this.id
  target_type                   = "ip"
  load_balancing_algorithm_type = "least_outstanding_requests"

  health_check {
    path     = "/"
    interval = 5
    timeout  = 3
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_lb_target_group" "green_tg" {
  protocol                      = "HTTP"
  port                          = 80
  deregistration_delay          = 60
  vpc_id                        = data.aws_vpc.this.id
  target_type                   = "ip"
  load_balancing_algorithm_type = "least_outstanding_requests"

  health_check {
    path     = "/"
    interval = 5
    timeout  = 3
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_lb_listener" "this_listener" {
  load_balancer_arn = aws_lb.this_alb.id
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/plain"
      message_body = "Not Found"
      status_code  = "404"
    }
  }
}

resource "aws_lb_listener" "test_listener" {
  load_balancer_arn = aws_lb.this_alb.id
  port              = 8090
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/plain"
      message_body = "Not Found"
      status_code  = "404"
    }
  }
}

resource "aws_lb_listener_rule" "blue_tg_based_routing" {
  listener_arn = aws_lb_listener.this_listener.arn
  priority     = 1

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.blue_tg.arn
  }

  condition {
    path_pattern {
      values = ["/*"]
    }
  }

  # We want CodeDeploy to be responsible for modifying LB listener, and not TF
  lifecycle {
    ignore_changes = [action]
  }
}

resource "aws_lb_listener_rule" "blue_tg_based_test_routing" {
  listener_arn = aws_lb_listener.test_listener.arn
  priority     = 1

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.blue_tg.arn
  }

  condition {
    path_pattern {
      values = ["/*"]
    }
  }


  # We want CodeDeploy to be responsible for modifying LB listener, and not TF
  lifecycle {
    ignore_changes = [action]
  }
}


resource "aws_ecs_service" "hello-world" {
  name             = "hello-world"
  cluster          = aws_ecs_cluster.this.id
  task_definition  = aws_ecs_task_definition.this_task_definition.arn
  desired_count    = 1
  launch_type      = "FARGATE"
  platform_version = "1.4.0"

  network_configuration {
    security_groups = [aws_security_group.ecs_sg.id, aws_security_group.alb_sg.id]
    subnets         = data.aws_subnet_ids.compute_subnet.ids
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.blue_tg.arn
    container_name   = "hello-world"
    container_port   = 80
  }

  deployment_controller {
    type = "CODE_DEPLOY"
  }

  tags = {
    "AWS/ALB" = aws_lb.this_alb.name
  }
}

resource "aws_appautoscaling_target" "hello-world" {
  max_capacity       = 10
  min_capacity       = 1
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.hello-world.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "this" {
  name               = "hello-world-autoscaling-policy"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.hello-world.resource_id
  scalable_dimension = aws_appautoscaling_target.hello-world.scalable_dimension
  service_namespace  = aws_appautoscaling_target.hello-world.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value       = 10
    scale_out_cooldown = 120
    scale_in_cooldown  = 180

    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.this_alb.arn_suffix}/${aws_lb_target_group.blue_tg.arn_suffix}"
    }
  }
}

resource "aws_cloudwatch_log_group" "fargate_containers_logs" {
  name              = "autoscaling-demo-container-logs"
  retention_in_days = 1
}

resource "aws_iam_role" "codeploy_service_role" {
  name               = "autoscaling-demo-codedeploy-service-role"
  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "",
      "Effect": "Allow",
      "Principal": {
        "Service": "codedeploy.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
}

resource "aws_iam_policy" "codeploy_service_role_policy" {
  name        = "autoscaling-demo-codedeploy-service-role-policy"
  description = "autoscaling-demo-codedeploy-service-role-policy"

  policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": [
          "ecs:DescribeServices",
          "ecs:CreateTaskSet",
          "ecs:UpdateServicePrimaryTaskSet",
          "ecs:DeleteTaskSet",
          "cloudwatch:DescribeAlarms",
          "sns:Publish",
          "iam:PassRole",
          "elasticloadbalancing:DescribeTargetGroups",
          "elasticloadbalancing:DescribeListeners",
          "elasticloadbalancing:ModifyListener",
          "elasticloadbalancing:DescribeRules",
          "elasticloadbalancing:ModifyRule",
          "lambda:InvokeFunction",
          "s3:GetObject",
          "s3:GetObjectMetadata",
          "s3:GetObjectVersion"
      ],
      "Resource": "*",
      "Effect": "Allow"
    }
  ]
}
EOF
}

resource "aws_iam_role_policy_attachment" "codeploy_service_role_policy_attachment" {
  role       = aws_iam_role.codeploy_service_role.name
  policy_arn = aws_iam_policy.codeploy_service_role_policy.arn
}

resource "aws_iam_role_policy_attachment" "AWSCodeDeployRole_polocy_attachment" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSCodeDeployRole"
  role       = aws_iam_role.codeploy_service_role.name
}

resource "aws_iam_role_policy_attachment" "AWSCodeDeployRoleForLambda_polocy_attachment" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSCodeDeployRoleForLambda"
  role       = aws_iam_role.codeploy_service_role.name
}

resource "aws_codedeploy_app" "this" {
  compute_platform = "ECS"
  name             = "autoscaling-demo"
}

resource "aws_codedeploy_deployment_group" "hello-world" {
  app_name               = aws_codedeploy_app.this.name
  deployment_config_name = "CodeDeployDefault.ECSAllAtOnce"
  deployment_group_name  = "hello-world"
  service_role_arn       = aws_iam_role.codeploy_service_role.arn

  auto_rollback_configuration {
    enabled = true
    events  = ["DEPLOYMENT_FAILURE"]
  }

  blue_green_deployment_config {
    deployment_ready_option {
      action_on_timeout = "CONTINUE_DEPLOYMENT"
    }

    terminate_blue_instances_on_deployment_success {
      action                           = "TERMINATE"
      termination_wait_time_in_minutes = 5
    }
  }

  deployment_style {
    deployment_option = "WITH_TRAFFIC_CONTROL"
    deployment_type   = "BLUE_GREEN"
  }

  ecs_service {
    cluster_name = aws_ecs_cluster.this.name
    service_name = aws_ecs_service.hello-world.name
  }

  load_balancer_info {
    target_group_pair_info {
      prod_traffic_route {
        listener_arns = [aws_lb_listener.this_listener.arn]
      }

      test_traffic_route {
        listener_arns = [aws_lb_listener.test_listener.arn]
      }

      target_group {
        name = aws_lb_target_group.blue_tg.name
      }

      target_group {
        name = aws_lb_target_group.green_tg.name
      }
    }
  }
}
