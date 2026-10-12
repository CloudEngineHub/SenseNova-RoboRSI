# Portable three-LIBERO Agent: three installed presets plus sealed ICL/tokenizer.
ARG AGENT_BASE_IMAGE
FROM ${AGENT_BASE_IMAGE}
ARG LIBERO_THREE_ASSETS=dist/agent/libero-three-assets
COPY ${LIBERO_THREE_ASSETS}/ /opt/roborsi-agent-assets/
COPY benchmarks/libero_three_combined/assets.lock.json /tmp/libero-three-assets.lock.json
COPY benchmarks/libero_three_combined/verify_agent_image.py /tmp/verify-libero-three-agent.py
ENV ROBORSI_LIBERO_LONGPP_ICL_ROOT=/opt/roborsi-agent-assets/longpp/packages \
    ROBORSI_LIBERO_ULTRA_ICL_ROOT=/opt/roborsi-agent-assets/ultra/packages \
    ROBORSI_LIBERO_PRO_ICL_ROOT=/opt/roborsi-agent-assets/pro/packages \
    ROBORSI_CONTEXT_TOKENIZER_PATH=/opt/roborsi-agent-assets/tokenizer.json
RUN python -B /tmp/verify-libero-three-agent.py \
    --lock /tmp/libero-three-assets.lock.json \
    && rm /tmp/verify-libero-three-agent.py /tmp/libero-three-assets.lock.json
