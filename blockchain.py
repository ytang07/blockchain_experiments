import hashlib
import json
from re import M
import re
from time import time
from urllib.parse import urlparse
from uuid import uuid4

import requests
from flask import Flask, jsonify, request

PREVIOUS_HASH = 'previous_hash'
PROOF = 'proof'
INDEX = 'index'
TRANSACTIONS = 'transactions'
SENDER = 'sender'
RECIPIENT = 'recipient'
AMOUNT = 'amount'
MESSAGE = 'message'

class Blockchain(object):
    def __init__(self):
        self.current_transactions = []
        self.chain = []
        self.nodes = set()

        self.new_block(previous_hash="Solar Power", proof=100)
    
    """
    @params address: address of the wallet, ie https://127.0.0.1:5001
    """
    def register_node(self, address):
        parsed_url = urlparse(address)
        if parsed_url.netloc:
            self.nodes.add(parsed_url.netloc)
        elif parsed_url.path:
            # handle url without scheme, ie 127.0.0.1:5001
            self.nodes.add(parsed_url.path)
        else:
            raise ValueError('Invalid URL')
    """
    @params chain: a Blockchain.chain (a list)
    @return: True if valid, False if not valid
    """
    def valid_chain(self, chain):
        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print('\n')
            # check that the hash of the block is correct
            last_block_hash = self.hash(last_block)
            if block[PREVIOUS_HASH] != last_block_hash:
                return False
            
            if not self.valid_proof(last_block[PROOF], block[PROOF], last_block_hash):
                return False
            
            last_block = block
            current_index += 1
        
        return True

    """
    Consensus Algorithm, replaces chain with the longest one in the network

    @return: True if our chain was replaced, False otherwise
    """
    def resolve_conflicts(self):
        neighbors = self.nodes
        new_chain = None

        max_length = len(self.chain)

        for node in neighbors:
            response = requests.get(f'http://{node}/chain')
            if response.status_code == 200:
                res = response.json()
                length = res['length']
                chain = res['chain']

                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain
        
        if new_chain:
            self.chain = new_chain
            return True

        return False

    """
    Create a new Block in the Blockchain

    @params proof: the proof returned by the algo
    @params previous_hash: the previous block's hash
    @return: the created new Block
    """
    def new_block(self, proof, previous_hash):
        block = {
            INDEX: len(self.chain) + 1,
            'timestamp': time(),
            TRANSACTIONS: self.current_transactions,
            PROOF: proof,
            PREVIOUS_HASH: previous_hash
        }

        # reset block
        self.current_transactions = []
        self.chain.append(block)

        return block

    """
    Adds a transaction to be processed to the "current_transactions"
    being kept track of by the block

    @params sender: sender address
    @params receiver: receiver address
    @params amount: amount received
    """
    def new_transaction(self, sender, recipient, amount):
        self.current_transactions.append({
            SENDER: sender,
            RECIPIENT: recipient,
            AMOUNT: amount
        })

        return self.last_block[INDEX] + 1

    @property
    def last_block(self):
        return self.chain[-1]
    
    """
    Creates the SHA256 hash for a block

    @params block: block
    """
    @staticmethod
    def hash(block):
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()
    
    """
    Simple proof of work algorithm
    - find a number p' such that hash(pp') contains 4 leading 0s
    - where p is the previous proof and p' is the new proof

    @params last_block: last Block (a dictionary)
    @returns: the hash (an int)
    """
    def proof_of_work(self, last_block):
        last_proof = last_block[PROOF]
        last_hash = self.hash(last_block)

        proof = 0
        while self.valid_proof(last_proof, proof, last_hash) is False:
            proof += 1
    
        return proof

    """
    validates proof 

    @returns: True if proof is valid, False otherwise
    """
    @staticmethod
    def valid_proof(last_proof, proof, last_hash):
        guess = f'{last_proof}{proof}{last_hash}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"
    
app = Flask(__name__)
node_id = str(uuid4()).replace('-', '')

blockchain = Blockchain()

@app.route('/mine', methods=['GET'])
def mine():
    last_block = blockchain.last_block
    proof = blockchain.proof_of_work(last_block)

    blockchain.new_transaction(
        sender='0',
        recipient=node_id,
        amount=1
    )

    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        MESSAGE: 'New Block Forged',
        INDEX: block[INDEX],
        TRANSACTIONS: block[TRANSACTIONS],
        PROOF: block[PROOF],
        PREVIOUS_HASH: block[PREVIOUS_HASH]
    }
    return jsonify(response), 200

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()
    required_values = [SENDER, RECIPIENT, AMOUNT]
    if not all(key in values for key in required):
        return 'Missing values', 400
    
    index = blockchain.new_transaction(values[SENDER], values[RECIPIENT], values[AMOUNT])
    response = {
        MESSAGE: f'Transaction will be added to Block {index}'
    }
    # 201 is the success code that indicates a new resources has been created
    return jsonify(response), 201

@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain)
    }
    return jsonify(response), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()
    nodes = values.get('nodes')
    if nodes is None:
        return 'Error: Please supply a valid list of nodes', 400
    for node in nodes:
        blockchain.register_node(node)
    
    response = {
        MESSAGE: 'New nodes have been added',
        'total_nodes': list(blockchain.nodes)
    }
    return jsonify(response), 201

@app.route('/nodes/resolve', methods = ['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            MESSAGE: 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            MESSAGE: 'Our chain is authoritative',
            'chain': blockchain.chain
        }
    return jsonify(response), 200

if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='Port to listen on')
    args = parser.parse_args()
    port = args.port

    app.run(host='0.0.0.0', port = port)
