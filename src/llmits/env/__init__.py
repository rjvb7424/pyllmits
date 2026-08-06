"""The game side of the harness: everything the model "sees" and "does".

    world        custom Crafter env + world builder
    observation  world -> text map, legend, PNG frames
    prompt       fills the prompt template
    actions      parses an action out of the model's reply
    success      the swappable objective checker
"""
