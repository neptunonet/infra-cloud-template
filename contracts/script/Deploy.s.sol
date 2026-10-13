// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {Counter} from "../src/Counter.sol";

/// @notice Class 7 (Web3 on L2): deploy the same bytecode to a local Anvil and
/// to Base Sepolia and compare gas/latency. Class 4: this is the script
/// contracts.yml runs on a tagged release.
/// The signer is NOT read here: it comes from the --private-key flag, so the
/// key lives only in your shell or in a GitHub environment secret, never in
/// this repository (and keys with or without 0x both work).
contract DeployScript is Script {
    function run() external returns (Counter) {
        vm.startBroadcast();

        Counter counter = new Counter();
        console.log("Counter deployed at:", address(counter));

        vm.stopBroadcast();
        return counter;
    }
}
