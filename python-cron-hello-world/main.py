import os

def init(ctx):
    # One time initialization comes here
    ctx.logger.info(f"Initialized... {os.environ.get('GREETING')}")

def handler(ctx, event):
    # Events Processing comes here
    ctx.logger.info(f"Handler {event}")
    return "Hello World"