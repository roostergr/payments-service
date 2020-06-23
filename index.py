from flask import Flask, request
from flask import _request_ctx_stack as stack
from pymongo import MongoClient
from bson.json_util import dumps
import os
import requests

from jaeger_client import Tracer, ConstSampler
from jaeger_client.reporter import NullReporter
from jaeger_client.codecs import B3Codec
from opentracing.propagation import Format
from opentracing_instrumentation.request_context import span_in_context

import logging
logging.basicConfig(level=logging.DEBUG)

tracer = Tracer(
    one_span_per_rpc=False,
    service_name='payments',
    reporter=NullReporter(),
    sampler=ConstSampler(decision=True),
    extra_codecs={Format.HTTP_HEADERS: B3Codec()}
)

def trace():
    '''
    Function decorator that creates opentracing span from incoming b3 headers
    '''
    def decorator(f):
        def wrapper(*args, **kwargs):
            request = stack.top.request
            try:
                # Create a new span context, reading in values (traceid,
                # spanid, etc) from the incoming x-b3-*** headers.
                span_ctx = tracer.extract(
                    Format.HTTP_HEADERS,
                    dict(request.headers)
                )
                app.logger.debug(dict(request.headers))
                # Note: this tag means that the span will *not* be
                # a child span. It will use the incoming traceid and
                # spanid. We do this to propagate the headers verbatim.
                rpc_tag = {tags.SPAN_KIND: tags.SPAN_KIND_RPC_SERVER}
                span = tracer.start_span(
                    operation_name='op', child_of=span_ctx, tags=rpc_tag
                )
            except Exception as e:
                # We failed to create a context, possibly due to no
                # incoming x-b3-*** headers. Start a fresh span.
                # Note: This is a fallback only, and will create fresh headers,
                # not propagate headers.
                span = tracer.start_span('op')
            with span_in_context(span):
                r = f(*args, **kwargs)
                return r
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

def getForwardHeaders(request):
    headers = {}

    incoming_headers = ['X-Request-Id', 'X-B3-Traceid', 'X-B3-Sampled', 'X-B3-Parentspanid', 'X-B3-Spanid', 'user-agent']

    for ihdr in incoming_headers:
        val = request.headers.get(ihdr)
        if val is not None:
            headers[ihdr] = val
            # print "incoming: "+ihdr+":"+val

    return headers


app = Flask(__name__)
client = MongoClient(host=os.environ['DB_HOST'])
db = client.usersdb

# This is only for the purpose of demo
if db.payment.count_documents({}) == 0:
  db.payment.insert({'from': 1, 'to': 2, 'amount': 100, 'currency': '$'})
  db.payment.insert({'from': 1, 'to': 2, 'amount': 200, 'currency': '$'})
  db.payment.insert({'from': 2, 'to': 1, 'amount': 100, 'currency': '$'})


@app.route('/ping')
def ping():
  return 'pong'


@app.route('/payments_from/<int:userid>')
@trace()
def payments_from(userid):
  payments_list = []
  for payment in db.payment.find({'from': userid}):
    payments_list.append(payment)
  app.logger.debug(getForwardHeaders(request))
  user_details = requests.get(
      'http://{}/user/{}'.format(os.environ['USERS_SERVICE'], userid), headers=getForwardHeaders(request))
  payment_details = {
      'version': 'v1',
      'user': user_details.json(),
      'payments': payments_list
  }
  return dumps(payment_details)
