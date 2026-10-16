ARG AGENT_IMAGE=roborsi-agent:isolated
FROM ${AGENT_IMAGE}
COPY tests/integration_tests/robots/libero/isolation_agent.py /usr/local/lib/python3.11/site-packages/roborsi_isolation_agent.py
