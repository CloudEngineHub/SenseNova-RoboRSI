# Export with python -m benchmarks.package after framework source registration.
FROM nvcr.io/nvidia/isaac-sim@sha256:68735a60b6c15c85e0dd0098570c6d2cc79e928f2d068ce2790aa43284ac165d
USER root
RUN apt-get update && apt-get install -y --no-install-recommends patch ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY build-lock.json fetch_native.py /opt/build/
RUN /isaac-sim/python.sh /opt/build/fetch_native.py
COPY patches/ /opt/build/patches/
RUN cd /opt/IsaacLab \
    && patch --batch --fuzz=0 -p1 < /opt/build/patches/isaaclab-2.3.2-isaacsim6.patch \
    && patch --batch --fuzz=0 -p1 < /opt/build/patches/isaaclab-native-dependencies.patch \
    && cd /opt/RoboLab \
    && patch --batch --fuzz=0 -p1 < /opt/build/patches/robolab-harness-transport.patch \
    && ln -s /isaac-sim /opt/IsaacLab/_isaac_sim \
    && ln -s /roborsi/assets/robolab /opt/RoboLab/assets
# NVIDIA deduplicates shared Python files through links into optional extensions.
# Materialize those files before removing the unused LLM extensions as a whole.
COPY prune_extensions.py /opt/build/prune_extensions.py
RUN /isaac-sim/python.sh /opt/build/prune_extensions.py --root /isaac-sim --report /opt/build/pruned.json
COPY python-runtime.sh /opt/robolab/bin/python
RUN chmod 755 /opt/robolab/bin/python
ENV PATH=/opt/robolab/bin:${PATH} \
    PYTHONPATH=/opt/roborsi:/opt/RoboLab \
    PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1 \
    ROBORSI_ROBOLAB_ROOT=/opt/RoboLab ROBORSI_ROBOLAB_PYTHON=/opt/robolab/bin/python \
    ISAACLAB_PATH=/opt/IsaacLab NVIDIA_DRIVER_CAPABILITIES=all \
    XDG_CACHE_HOME=/tmp/cache MPLCONFIGDIR=/tmp/matplotlib \
    TORCH_EXTENSIONS_DIR=/tmp/torch-extensions WARP_CACHE_PATH=/tmp/warp
COPY native-requirements.txt native-image.constraints.txt /opt/build/
RUN --mount=type=cache,id=robolab-native-pip,target=/root/.cache/pip \
    PIP_CACHE_DIR=/root/.cache/pip python -m pip install pip==26.2.1 \
    && PIP_CACHE_DIR=/root/.cache/pip python -m pip install --build-constraint /opt/build/native-image.constraints.txt \
    -c /opt/build/native-image.constraints.txt \
    -r /opt/build/native-requirements.txt \
    -e /opt/IsaacLab/source/isaaclab \
    -e /opt/IsaacLab/source/isaaclab_assets \
    -e /opt/IsaacLab/source/isaaclab_tasks \
    && python -m pip check
WORKDIR /opt/roborsi
COPY benchmark-runtime/ /opt/roborsi/
RUN python -P -c "from pathlib import Path; from roborsi.benchmarks.runtime_source import verify_benchmark_runtime; from robots.robolab.native import native_root, verify_native_source; verify_benchmark_runtime(Path('/opt/roborsi'), 'robolab'); verify_native_source(native_root())"
# The executor uses the host UID. NVIDIA's top-level directory is 0750;
# its contents already have public read/traverse permissions.
RUN chmod a+rx /isaac-sim
ENV OMNI_KIT_ACCEPT_EULA=YES
USER isaac-sim
ENTRYPOINT []
HEALTHCHECK NONE
CMD ["python", "-P", "-m", "roborsi.evaluation.service_host", "--kind", "benchmark", "--factory", "robots.robolab.benchmark_service:make_robolab_benchmark", "--host", "0.0.0.0", "--port", "8000"]
