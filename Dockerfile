FROM python:3.9

# Install necessary packages and dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    ca-certificates \
    libasound2 \
    wget \
    libgstreamer1.0-0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly && \
    rm -rf /var/lib/apt/lists/*

# Install OpenSSL from source
RUN wget -O - https://www.openssl.org/source/openssl-1.1.1w.tar.gz | tar zxf - && \
    cd openssl-1.1.1w && \
    ./config --prefix=/usr/local && \
    make -j $(nproc) && \
    make install_sw install_ssldirs && \
    ldconfig -v

# Set environment variables
ENV SSL_CERT_DIR=/etc/ssl/certs
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
# Note: Ensure SPEECHSDK_ROOT is defined correctly if you're using it for Azure Speech SDK or similar
ENV LD_LIBRARY_PATH="$SPEECHSDK_ROOT/lib/x64:$LD_LIBRARY_PATH"

WORKDIR /src

# Copy your application code to the container
COPY ./ .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Command to run the application
CMD ["uvicorn", "Pronunciation_api:app", "--host", "0.0.0.0", "--port", "8080"]
