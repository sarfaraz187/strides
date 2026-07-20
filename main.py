from dotenv import load_dotenv
from data.db import init_db
from src.auth import get_valid_access_token

load_dotenv()


def main():
    init_db()

    print("----------------------------------")
    print("!!!!!!! Hello from strides. !!!!!!")
    print("----------------------------------")

    token = get_valid_access_token("sarfarazflame@gmail.com")
    print(token)


if __name__ == "__main__":
    main()
