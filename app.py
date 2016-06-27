import os
import time
import numpy as np
from flask import *
from flask_socketio import *
from celery import Celery, chain
from pattern.web import Twitter
from sklearn.externals import joblib

path = os.path.realpath('') + '/scripts/'
sys.path.append(path)


# Initialize and configure Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret'
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'
app.config['SOCKETIO_REDIS_URL'] = 'redis://localhost:6379/0'
app.config['BROKER_TRANSPORT'] = 'redis'
app.config['CELERY_ACCEPT_CONTENT'] = ['pickle']

# Initialize SocketIO
socketio = SocketIO(app, message_queue=app.config['SOCKETIO_REDIS_URL'])

# Initialize and configure Celery
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# Load sentiment classification model
vectorizer = joblib.load(path + 'vectorizer.pkl')
classifier = joblib.load(path + 'classifier.pkl')


# Function to transform and classify a tweet as positive or negative sentiment
def classify_tweet(tweet):
    pred = classifier.predict(vectorizer.transform(np.array([tweet.text])))

    if pred[0] == 1:
        return '1'
    else:
        return '-1'


# Various tasks used for testing
@celery.task
def add(x, y):
    return x + y


@celery.task
def multiply(x, y):
    return x * y


@celery.task
def generate_message(message, queue):
    time.sleep(1)
    local = SocketIO(message_queue=queue)
    local.emit('task complete', {'data': 'The answer is: {0}'.format(str(message))})


# Main page tasks
@celery.task
def create_stream(phrase, queue):
    local = SocketIO(message_queue=queue)
    stream = Twitter().stream(phrase, timeout=30)

    for i in range(100):
        stream.update()
        for tweet in reversed(stream):
            local.emit('tweet', {'id': str(i),
                                 'data': str(tweet.text.encode('ascii', 'ignore')),
                                 'sentiment': classify_tweet(tweet)})
        stream.clear()
        time.sleep(1)


# Various routes used for testing
@app.route('/hello/', methods=['GET'])
@app.route('/hello/<name>', methods=['GET'])
def hello(name=None):
    return render_template('hello.html', name=name)


@app.route('/message', methods=['GET'])
def message():
    return render_template('message.html')


@app.route('/d3', methods=['GET'])
def d3():
    return render_template('d3.html')


@app.route('/submit/<int:x>/<int:y>', methods=['POST'])
def submit(x, y):
    queue = app.config['SOCKETIO_REDIS_URL']
    chain(add.s(x, y), multiply.s(10), generate_message.s(queue)).apply_async()
    return 'Waiting for a reply...'


# Main page routes
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/twitter/<phrase>', methods=['POST'])
def twitter(phrase):
    queue = app.config['SOCKETIO_REDIS_URL']
    create_stream.apply_async(args=[phrase, queue])
    return 'Establishing connection...'


if __name__ == '__main__':
    socketio.run(app, debug=True)
