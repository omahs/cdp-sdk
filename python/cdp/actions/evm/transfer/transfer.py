from decimal import Decimal
from typing import TypeVar

from web3 import Web3

from cdp.api_clients import ApiClients
from cdp.evm_server_account import EvmServerAccount
from cdp.evm_smart_account import EvmSmartAccount

from .types import TransferExecutionStrategy, TransferOptions, TransferResult
from .utils import get_chain_config

# ERC20 ABI for calling decimals() and other token functions
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# Type for account
T = TypeVar("T", bound=EvmServerAccount | EvmSmartAccount)


async def transfer(
    api_clients: ApiClients,
    from_account: T,
    transfer_args: TransferOptions,
    transfer_strategy: TransferExecutionStrategy,
) -> TransferResult:
    """Transfer an amount of a token from an account to another account.

    Args:
        api_clients: The API clients to use to send the transaction
        from_account: The account to send the transaction from
        transfer_args: The options for the transfer
        transfer_strategy: The strategy to use to execute the transfer

    Returns:
        The result of the transfer

    """
    # Create a Web3 client for the specified network
    chain_config = get_chain_config(transfer_args.network)
    w3 = Web3(Web3.HTTPProvider(chain_config["rpc_url"]))

    # Determine the recipient address
    to_address = (
        transfer_args.to.address if hasattr(transfer_args.to, "address") else transfer_args.to
    )

    # Calculate the value to transfer
    value = await _calculate_value(w3, transfer_args)

    # Execute the transfer using the provided strategy
    tx_hash = await transfer_strategy.execute_transfer(
        api_clients=api_clients,
        from_account=from_account,
        transfer_args=transfer_args,
        to=to_address,
        value=value,
    )

    # Wait for the result of the transfer
    result = await transfer_strategy.wait_for_result(
        api_clients=api_clients, w3=w3, from_account=from_account, hash=tx_hash
    )

    return result


async def _calculate_value(w3: Web3, transfer_args: TransferOptions) -> int:
    """Calculate the value to transfer based on the transfer arguments.

    Args:
        w3: The Web3 client
        transfer_args: The transfer arguments

    Returns:
        The value to transfer

    """
    # If amount is already an integer, return it directly
    if isinstance(transfer_args.amount, int):
        return transfer_args.amount

    # Otherwise, convert the string amount to an integer based on the token's decimals
    amount_decimal = Decimal(transfer_args.amount)

    # Get the token decimals
    if transfer_args.token == "eth":
        decimals = 18
    elif transfer_args.token == "usdc":
        decimals = 6
    else:
        # For other tokens, get the decimals from the contract
        token_contract = w3.eth.contract(
            address=Web3.to_checksum_address(transfer_args.token), abi=ERC20_ABI
        )
        decimals = await token_contract.functions.decimals().call()

    # Calculate the value with the right number of decimals
    value = int(amount_decimal * (10**decimals))
    return value
