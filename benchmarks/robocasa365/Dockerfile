# RoboCasa365 Target50 benchmark service. Build only the context produced by
# python -m benchmarks.package --benchmark robocasa365 (see BUILD.md).
#
# The base is the Target50 environment image: Python 3.10 at /opt/rpent-py310
# with the pinned RoboCasa, robosuite, mujoco and RLDX-1 stack, the kitchen
# assets at /opt/robocasa-assets and RLDX-1 weights at /opt/rldx. BUILD.md
# lists how it was assembled and what it contains.
ARG ROBOCASA365_BASE_IMAGE=ghcr.io/opensensenova/sensenova-roborsi-robocasa365@sha256:8494fef17ee5979a072967632a2cb6ca885a165e87b01fb88d40c9f88b5b82e1
FROM ${ROBOCASA365_BASE_IMAGE}
# The base also carried the earlier one-process HEART application. A Benchmark
# image holds only the native benchmark and its service, so the planner, its
# model clients and that application are removed; its BUILD records, which
# describe the base, stay under /opt/heart-robocasa/BUILD.
COPY agent-packages.txt /tmp/agent-packages.txt
# The base registers anthropic twice (a stale 1.7.0 record next to 1.8.0), so
# the uninstall runs until no listed distribution is left.
RUN for pass in 1 2; do \
      /opt/rpent-py310/bin/python -m pip uninstall -y -r /tmp/agent-packages.txt; \
    done \
    && cd /opt/heart-robocasa \
    && rm -rf README.md bin driver memory src target50.json /tmp/agent-packages.txt
ENV PATH=/opt/rpent-py310/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONPATH=/opt/roborsi PYTHONDONTWRITEBYTECODE=1 \
    HEART_REPO= HEART_ROBOCASA_HOME= HEART_RESET_TIMEOUT_S=
WORKDIR /opt/roborsi
COPY benchmark-runtime/ /opt/roborsi/
RUN python -B -c "from pathlib import Path; from roborsi.benchmarks.runtime_source import verify_benchmark_runtime; verify_benchmark_runtime(Path('/opt/roborsi'), 'robocasa365')"
ENTRYPOINT []
# The same image serves RLDX-1 when started with
#   python robots/robocasa/vla_server.py --model-path /opt/rldx/RLDX-1-FT-RC365 \
#     --transport http --host 0.0.0.0 --port 8001
CMD ["python", "-m", "roborsi.evaluation.service_host", "--kind", "benchmark", "--factory", "robots.robocasa.benchmark_service:make_robocasa365_benchmark", "--host", "0.0.0.0", "--port", "8000"]
