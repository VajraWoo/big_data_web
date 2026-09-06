FROM ghcr.io/astral-sh/uv:0.12.9@sha256:8b940d3a9d65bed080436972241af2e21c84b5e8c9193f7014ed71479ee795ff AS uv
FROM spark:4.1.2-scala2.13-java21-python3-ubuntu@sha256:8924a12c1365c5d2e02cfac93954a51a9f55aeb5ef4632a39331692fc1164422

USER root
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_PYTHON_INSTALL_DIR=/opt/python
RUN uv python install 3.12.12 --no-progress \
    && ln -s /opt/python/cpython-3.12.12-linux-x86_64-gnu/bin/python3.12 /usr/local/bin/python3 \
    && /usr/local/bin/python3 --version
RUN uv venv --python /usr/local/bin/python3 /opt/text-profile \
    && uv pip install --python /opt/text-profile/bin/python --index-url https://download.pytorch.org/whl/cpu torch==2.7.1 \
    && uv pip install --python /opt/text-profile/bin/python fasttext==0.9.3 numpy==1.26.4 tokenizers==0.22.0 pyyaml==6.0.3 vaderSentiment==3.3.2 transformers==4.57.1 sentence-transformers==5.1.2 \
    && /opt/text-profile/bin/python -c "import fasttext, tokenizers, yaml, vaderSentiment, torch, transformers, sentence_transformers; print(torch.__version__)"
ENV VIRTUAL_ENV=/opt/text-profile
ENV PATH="/opt/text-profile/bin:${PATH}"
ENV PYSPARK_PYTHON=/opt/text-profile/bin/python
ENV PYSPARK_DRIVER_PYTHON=/opt/text-profile/bin/python
ENV HF_HOME=/models/huggingface
ADD --checksum=sha256:35f189464f3895855a93c2b71529cca120d94bee98bc337f34ab2ffd998d3d80 https://repo.maven.apache.org/maven2/org/mongodb/spark/mongo-spark-connector_2.13/11.1.0/mongo-spark-connector_2.13-11.1.0.jar /opt/spark/jars/mongo-spark-connector_2.13-11.1.0.jar
ADD --checksum=sha256:341880078296edd762756440e9d6b1d6d2bf4d6b91975c2638e3da611f28b1c2 https://repo.maven.apache.org/maven2/org/mongodb/mongodb-driver-sync/5.1.4/mongodb-driver-sync-5.1.4.jar /opt/spark/jars/mongodb-driver-sync-5.1.4.jar
ADD --checksum=sha256:ae3dbfd439d5afe9e0d6abbd61ef27d858ca2d38083bb7361f69e243aff31dec https://repo.maven.apache.org/maven2/org/mongodb/mongodb-driver-core/5.1.4/mongodb-driver-core-5.1.4.jar /opt/spark/jars/mongodb-driver-core-5.1.4.jar
ADD --checksum=sha256:bba556a8acd4e87545c1b9a1cb25c12ce9587ed5bf01685f236c5d92abf1e676 https://repo.maven.apache.org/maven2/org/mongodb/bson/5.1.4/bson-5.1.4.jar /opt/spark/jars/bson-5.1.4.jar
ADD --checksum=sha256:698b2b9a10fdd49a3ed99ad2b7bcc8e797639c8c4a5c974de7f6fc8654bda655 https://repo.maven.apache.org/maven2/org/mongodb/bson-record-codec/5.1.4/bson-record-codec-5.1.4.jar /opt/spark/jars/bson-record-codec-5.1.4.jar
COPY connector-jars.sha256 /opt/spark/connector-jars.sha256
RUN cd /opt/spark/jars && sha256sum -c /opt/spark/connector-jars.sha256 \
    && chmod 644 /opt/spark/jars/*mongodb*.jar /opt/spark/jars/mongo-spark*.jar /opt/spark/jars/bson*.jar
USER spark
