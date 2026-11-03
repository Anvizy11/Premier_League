"""Local entry point. Run with python app.py or flask --app app."""

from premier_league import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=False, port=5001)
