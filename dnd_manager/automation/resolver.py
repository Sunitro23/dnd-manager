from dnd_manager.automation.contracts import Resolution


def resolve(specifications, target, context):
    return resolve_effects(tuple(map_effects(specifications)), target, context)


def map_effects(specifications):
    from dnd_manager.automation.compiler import compile_effect
    return (compile_effect(specification) for specification in specifications)


def resolve_effects(effects, target, context):
    resolution = Resolution(target, ())
    for effect in effects:
        resolution = apply_effect(resolution, effect, context)
    return resolution


def apply_effect(resolution, effect, context):
    target, event = effect.apply(resolution.target, context)
    return Resolution(target, resolution.events + (event,))
