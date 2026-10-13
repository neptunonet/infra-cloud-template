// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Counter
/// @notice Deliberately simple example contract for class 4 (CI/CD: forge
/// test on every PR) and class 7 (deploy the same bytecode to Sepolia and
/// to Base Sepolia, compare gas/latency on both explorers).
contract Counter {
    uint256 public number;

    event NumberChanged(uint256 previousValue, uint256 newValue);

    /// @notice Overwrite the stored number.
    function setNumber(uint256 newNumber) public {
        emit NumberChanged(number, newNumber);
        number = newNumber;
    }

    /// @notice Increment the stored number by one.
    function increment() public {
        uint256 previous = number;
        number = previous + 1;
        emit NumberChanged(previous, number);
    }
}
