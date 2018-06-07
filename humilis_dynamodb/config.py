"""Configuration options."""


import os

# The DynamoDB write capacity when we are not pushing data to it
BASELINE_WRITE_CAPACITY = 1

# Report in stdin every time this # of items are pushed to DynamoDB
REPORT_EVERY = 1000

# DynamoDB write capacity during push
PUSH_WRITE_CAPACITY = int(
    os.environ.get("HUMILIS_DYNAMODB_PUSH_WRITE_CAPACITY", 800))

# Initial sleep time between DynamoDB write requests. This value will be 
# dynamically modified to maximise throughput.
INITIAL_WAIT = 0.01
# We are hitting DynamoDB too hard, multiply the wait time by this factor
WAIT_MORE_FACTOR = 1.5
# We are NOT hitting DynamoDB too hard, multiply the wait time by this factor
WAIT_LESS_FACTOR = 0.9
# If we are going to wait more than this, then something is really wrong
MAX_WAIT = 100

# Seconds to wait for the DynamoDB table throughput to be scaled up or down
WAIT_TO_SCALE = 30
