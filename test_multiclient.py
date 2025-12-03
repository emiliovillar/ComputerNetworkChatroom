print("""
MULTI-CLIENT CHAT TEST

Terminal 1: python client.py --name Alice
            > JOIN lobby
            > MSG lobby Hello from Alice!

Terminal 2: python client.py --name Bob
            > JOIN lobby  
            > MSG lobby Hello from Bob!

Expected: Both clients see each other's messages
""")
