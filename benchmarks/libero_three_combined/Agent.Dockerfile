# Portable three-LIBERO Agent: three installed presets plus sealed ICL/tokenizer.
ARG AGENT_BASE_IMAGE
FROM ${AGENT_BASE_IMAGE}
ARG LIBERO_THREE_ASSETS=dist/agent/libero-three-assets
COPY ${LIBERO_THREE_ASSETS}/ /opt/heart-agent-assets/
COPY benchmarks/libero_three_combined/assets.lock.json /tmp/libero-three-assets.lock.json
COPY benchmarks/libero_three_combined/verify_agent_image.py /tmp/verify-libero-three-agent.py
ENV HEART_LIBERO_LONGPP_ICL_ROOT=/opt/heart-agent-assets/longpp/packages \
    HEART_LIBERO_ULTRA_ICL_ROOT=/opt/heart-agent-assets/ultra/packages \
    HEART_LIBERO_PRO_ICL_ROOT=/opt/heart-agent-assets/pro/packages \
    HEART_CONTEXT_TOKENIZER_PATH=/opt/heart-agent-assets/tokenizer.json
RUN python -B /tmp/verify-libero-three-agent.py \
    --lock /tmp/libero-three-assets.lock.json \
    && rm /tmp/verify-libero-three-agent.py /tmp/libero-three-assets.lock.json
