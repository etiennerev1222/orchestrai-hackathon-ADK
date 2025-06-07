#!/bin/bash

cd $(dirname "$0")

AGENTS=(
    'decomposition_agent'
    'development_agent'
    'evaluator'
    'reformulator'
    'research_agent'
    'testing_agent'
    'user_interaction_agent'
    'validator'
)

for AGENT in "\decomposition_agent development_agent evaluator reformulator research_agent testing_agent user_interaction_agent validator"; do
    echo "Building $AGENT..."
    docker build -t orchestrai/$AGENT:latest -f $AGENT/Dockerfile ./$AGENT
done
