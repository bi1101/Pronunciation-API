FROM python:3.9

WORKDIR /src

COPY ./ .

RUN wget -O - https://www.openssl.org/source/openssl-1.1.1w.tar.gz | tar zxf - 
RUN cd openssl-1.1.1w && \
        ./config --prefix=/usr/local && \
        make -j $(nproc) && \
        make install_sw install_ssldirs && \
        ldconfig -v

RUN apt-get update && \
    apt-get install build-essential libssl-dev ca-certificates libasound2 wget

RUN apt install libgstreamer1.0-0 \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-ugly -y
    
ENV SSL_CERT_DIR=/etc/ssl/certs
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
ENV LD_LIBRARY_PATH="$SPEECHSDK_ROOT/lib/x64:$LD_LIBRARY_PATH"

RUN pip install --no-cache-dir --upgrade -r requirements.txt

CMD ["uvicorn", "Pronunciation_api:app", "--host", "0.0.0.0", "--port", "8080"]
