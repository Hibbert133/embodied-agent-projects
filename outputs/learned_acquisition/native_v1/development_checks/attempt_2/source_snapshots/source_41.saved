"""Independent v1 fixed-policy task registry; historical push factories unchanged."""
TASK_POLICIES={"push-v3":"SawyerPushV3Policy","reach-v3":"SawyerReachV3Policy","door-open-v3":"SawyerDoorOpenV3Policy"}


def create_task_environment(task,seed):
    if task not in TASK_POLICIES: raise ValueError("unregistered task")
    import gymnasium as gym
    import metaworld  # noqa: F401 - registers the installed environments
    return gym.make("Meta-World/MT1",env_name=task,seed=seed)


def create_task_policy(task):
    if task not in TASK_POLICIES: raise ValueError("unregistered task")
    import metaworld.policies as policies
    return getattr(policies,TASK_POLICIES[task])()
