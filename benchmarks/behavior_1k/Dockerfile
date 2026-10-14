# Build only from the context produced by python -m benchmarks.package.
# BEHAVIOR_RUNTIME_IMAGE must be the digest in build-lock.json.
ARG BEHAVIOR_RUNTIME_IMAGE
FROM ${BEHAVIOR_RUNTIME_IMAGE}
USER root
ENV PATH=/opt/conda/envs/behavior/bin:${PATH}
WORKDIR /opt/roborsi
ARG BEHAVIOR_COMMIT=b1979916ec1549b10a4e65e630bc6504a9af1b00
RUN git clone https://github.com/StanfordVL/BEHAVIOR-1K.git /workspace/BEHAVIOR-1K \
    && git -C /workspace/BEHAVIOR-1K checkout --detach ${BEHAVIOR_COMMIT} \
    && python -m pip install --no-deps -e /workspace/BEHAVIOR-1K/OmniGibson -e /workspace/BEHAVIOR-1K/bddl3
COPY requirements.txt /opt/requirements-service.txt
RUN python -m pip install --require-hashes -r /opt/requirements-service.txt \
    && python -m pip check \
    && python -m pip freeze --all > /opt/native-environment.lock.txt
COPY benchmark-runtime/ /opt/roborsi/
COPY source.json build.json build-lock.json /opt/build-evidence/
ENV PYTHONPATH=/opt/roborsi \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    ROBORSI_BEHAVIOR_NATIVE=/workspace/BEHAVIOR-1K \
    ROBORSI_BEHAVIOR_ASSETS=/roborsi/assets/behavior_1k \
    ROBORSI_BEHAVIOR_CATALOG=/roborsi/assets/behavior_1k-catalog \
    OMNIGIBSON_DATA_PATH=/roborsi/assets/behavior_1k \
    OMNIGIBSON_HEADLESS=True OMNI_KIT_ACCEPT_EULA=YES \
    NVIDIA_DRIVER_CAPABILITIES=all
RUN python -B -c "from pathlib import Path; from roborsi.benchmarks.runtime_source import verify_benchmark_runtime; verify_benchmark_runtime(Path('/opt/roborsi'), 'behavior_1k')"
RUN python -B -c "from robots.behavior_1k.benchmark_service import BehaviorBenchmark; BehaviorBenchmark().runtime_info()"
EXPOSE 8000
ENTRYPOINT []
CMD ["python", "-m", "roborsi.evaluation.service_host", "--kind", "benchmark", "--factory", "robots.behavior_1k.benchmark_service:make_behavior_benchmark", "--host", "0.0.0.0", "--port", "8000"]
