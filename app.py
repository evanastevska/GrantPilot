import queue
import threading
from flask import Flask, request, Response, stream_with_context, render_template
from agent import run_agent

app = Flask(__name__)
progress_queue = queue.Queue()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/run', methods=['POST'])
def run():
    grant_input = request.form.get('grant_input', '')
    email = request.form.get('email', '')

    while not progress_queue.empty():
        try:
            progress_queue.get_nowait()
        except queue.Empty:
            break

    thread = threading.Thread(
        target=run_agent,
        args=(grant_input, email, progress_queue),
        daemon=True,
    )
    thread.start()
    return {'status': 'started'}, 200


@app.route('/stream')
def stream():
    def generate():
        while True:
            msg = progress_queue.get()
            yield f"data: {msg}\n\n"
            if msg.startswith('DONE:') or msg.startswith('ERROR:'):
                break

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


if __name__ == '__main__':
    app.run(debug=True, port=5000)