from flask import Flask
from pymongo import MongoClient
from bson.json_util import dumps
import os
import requests

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
def payments_from(userid):
  payments_list = []
  for payment in db.payment.find({'from': userid}):
    payments_list.append(payment)
  user_details = requests.get(
      'http://{}/user/{}'.format(os.environ['USERS_SERVICE'], userid))
  payment_details = {
      'version': 'v2',
      'user': user_details.json(),
      'payments': payments_list
  }
  return dumps(payment_details)
