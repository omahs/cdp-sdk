from typing import cast

from eth_typing import HexStr
from web3 import Web3

from cdp.actions.evm.send_user_operation import send_user_operation
from cdp.actions.evm.wait_for_user_operation import wait_for_user_operation
from cdp.api_clients import ApiClients
from cdp.evm_call_types import EncodedCall
from cdp.evm_smart_account import EvmSmartAccount

from .types import TransferExecutionStrategy, TransferOptions, TransferResult
from .utils import get_erc20_address

# ERC20 ABI for function encoding
ERC20_ABI = [
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


class SmartAccountTransferStrategy(TransferExecutionStrategy):
    """Transfer execution strategy for EvmSmartAccount."""

    async def execute_transfer(
        self,
        api_clients: ApiClients,
        from_account: EvmSmartAccount,
        transfer_args: TransferOptions,
        to: str,
        value: int,
    ) -> HexStr:
        """Execute a transfer from a smart account.

        Args:
            api_clients: The API clients
            from_account: The account to transfer from
            transfer_args: The transfer options
            to: The recipient address
            value: The amount to transfer

        Returns:
            The transaction hash

        """
        if transfer_args.token == "eth":
            # For ETH transfers, we send directly to the recipient
            result = await send_user_operation(
                api_clients=api_clients,
                smart_account=from_account,
                calls=[EncodedCall(to=to, value=str(value), data="0x")],
                network=transfer_args.network,
                paymaster_url=None,
            )

            return cast(HexStr, result["user_op_hash"])
        else:
            # For token transfers, we need to interact with the ERC20 contract
            erc20_address = get_erc20_address(transfer_args.token, transfer_args.network)

            # Encode function calls using Web3
            w3 = Web3()
            contract = w3.eth.contract(abi=ERC20_ABI)

            # Create approve call
            approve_data = contract.encodeABI(fn_name="approve", args=[to, value])

            # Create transfer call
            transfer_data = contract.encodeABI(fn_name="transfer", args=[to, value])

            # Send user operation with both calls
            result = await send_user_operation(
                api_clients=api_clients,
                smart_account=from_account,
                calls=[
                    EncodedCall(to=erc20_address, data=approve_data),
                    EncodedCall(to=erc20_address, data=transfer_data),
                ],
                network=transfer_args.network,
                paymaster_url=None,
            )

            return cast(HexStr, result["user_op_hash"])

    async def wait_for_result(
        self, api_clients: ApiClients, w3: Web3, from_account: EvmSmartAccount, hash: HexStr
    ) -> TransferResult:
        """Wait for the result of a transfer.

        Args:
            api_clients: The API clients
            w3: The Web3 client
            from_account: The account that sent the transfer
            hash: The transaction hash

        Returns:
            The result of the transfer

        """
        result = await wait_for_user_operation(
            api_clients=api_clients,
            smart_account_address=from_account.address,
            user_op_hash=hash,
        )

        if result["status"] == "complete":
            return TransferResult(status="success", transaction_hash=hash)
        else:
            chain_id = w3.eth.chain_id
            explorer_url = f"https://{'sepolia.' if chain_id == 84532 else ''}basescan.org"

            raise Exception(
                f"Transaction failed. Check the transaction on the explorer: "
                f"{explorer_url}/tx/{hash}"
            )


# Create the instance for use by the transfer function
smart_account_transfer_strategy = SmartAccountTransferStrategy()
