import itertools

import brownie
import pytest

TYPE_WEIGHTS = [5e17, 1e19]
GAUGE_WEIGHTS = [1e19, 1e18, 5e17]
GAUGE_TYPES = [0, 0, 1]

MONTH = 86400 * 30
WEEK = 7 * 86400


@pytest.fixture(scope="module", autouse=True)
def minter_setup(accounts, mock_lp_token, token, minter, gauge_controller, three_gauges, chain):
    token.set_minter(minter, {"from": accounts[0]})
    token.transfer(minter, 1_303_030_303 * 10 ** 18, {"from": accounts[0]})

    # ensure the tests all begin at the start of the epoch week
    chain.mine(timestamp=(chain.time() / WEEK + 1) * WEEK)

    # set types
    for weight in TYPE_WEIGHTS:
        gauge_controller.add_type(b"Liquidity", weight, {"from": accounts[0]})

    # add gauges
    for i in range(3):
        gauge_controller.add_gauge(
            three_gauges[i], GAUGE_TYPES[i], GAUGE_WEIGHTS[i], {"from": accounts[0]}
        )

    # transfer tokens
    for acct in accounts[1:4]:
        mock_lp_token.transfer(acct, 1e18, {"from": accounts[0]})

    # approve gauges
    for gauge, acct in itertools.product(three_gauges, accounts[1:4]):
        mock_lp_token.approve(gauge, 1e18, {"from": acct})


def test_mint(accounts, chain, three_gauges, minter, token):

    three_gauges[0].deposit(1e18, {"from": accounts[1]})

    chain.sleep(MONTH)
    minter.mint(three_gauges[0], {"from": accounts[1]})
    expected = three_gauges[0].integrate_fraction(accounts[1])

    assert expected > 0
    assert token.balanceOf(accounts[1]) == expected
    assert minter.minted(accounts[1], three_gauges[0]) == expected


def test_mint_immediate(accounts, chain, three_gauges, minter, token):
    three_gauges[0].deposit(1e18, {"from": accounts[1]})
    t0 = chain.time()
    chain.sleep((t0 + WEEK) // WEEK * WEEK - t0 + 1)  # 1 second more than enacting the weights

    minter.mint(three_gauges[0], {"from": accounts[1]})
    balance = token.balanceOf(accounts[1])

    assert balance > 0
    assert minter.minted(accounts[1], three_gauges[0]) == balance


def test_mint_multiple_same_gauge(accounts, chain, three_gauges, minter, token):
    three_gauges[0].deposit(1e18, {"from": accounts[1]})

    chain.sleep(MONTH)
    minter.mint(three_gauges[0], {"from": accounts[1]})
    balance = token.balanceOf(accounts[1])

    chain.sleep(MONTH)
    minter.mint(three_gauges[0], {"from": accounts[1]})
    expected = three_gauges[0].integrate_fraction(accounts[1])
    final_balance = token.balanceOf(accounts[1])

    assert final_balance > balance
    assert final_balance == expected
    assert minter.minted(accounts[1], three_gauges[0]) == expected


def test_mint_multiple_gauges(accounts, chain, three_gauges, minter, token):
    for i in range(3):
        three_gauges[i].deposit((i + 1) * 10 ** 17, {"from": accounts[1]})

    chain.sleep(MONTH)

    for i in range(3):
        minter.mint(three_gauges[i], {"from": accounts[1]})

    total_minted = 0
    for i in range(3):
        gauge = three_gauges[i]
        minted = minter.minted(accounts[1], gauge)
        assert minted == gauge.integrate_fraction(accounts[1])
        total_minted += minted

    assert token.balanceOf(accounts[1]) == total_minted


def test_mint_after_withdraw(accounts, chain, three_gauges, minter, token):
    three_gauges[0].deposit(1e18, {"from": accounts[1]})

    chain.sleep(2 * WEEK)
    three_gauges[0].withdraw(1e18, {"from": accounts[1]})
    minter.mint(three_gauges[0], {"from": accounts[1]})

    assert token.balanceOf(accounts[1]) > 0


def test_mint_multiple_after_withdraw(accounts, chain, three_gauges, minter, token):
    three_gauges[0].deposit(1e18, {"from": accounts[1]})

    chain.sleep(10)
    three_gauges[0].withdraw(1e18, {"from": accounts[1]})
    minter.mint(three_gauges[0], {"from": accounts[1]})
    balance = token.balanceOf(accounts[1])

    chain.sleep(10)
    minter.mint(three_gauges[0], {"from": accounts[1]})

    assert token.balanceOf(accounts[1]) == balance


def test_no_deposit(accounts, chain, three_gauges, minter, token):
    minter.mint(three_gauges[0], {"from": accounts[1]})

    assert token.balanceOf(accounts[1]) == 0
    assert minter.minted(accounts[1], three_gauges[0]) == 0


def test_mint_wrong_gauge(accounts, chain, three_gauges, minter, token):
    three_gauges[0].deposit(1e18, {"from": accounts[1]})

    chain.sleep(MONTH)
    minter.mint(three_gauges[1], {"from": accounts[1]})

    assert token.balanceOf(accounts[1]) == 0
    assert minter.minted(accounts[1], three_gauges[0]) == 0
    assert minter.minted(accounts[1], three_gauges[1]) == 0


def test_mint_not_a_gauge(accounts, minter):
    with brownie.reverts("dev: gauge is not added"):
        minter.mint(accounts[1], {"from": accounts[0]})


def test_mint_before_inflation_begins(accounts, chain, three_gauges, minter, token):
    three_gauges[0].deposit(1e18, {"from": accounts[1]})

    chain.sleep(token.start_epoch_time() - chain.time() - 5)
    minter.mint(three_gauges[0], {"from": accounts[1]})

    assert token.balanceOf(accounts[1]) == 0
    assert minter.minted(accounts[1], three_gauges[0]) == 0

def test_recover_balance(accounts, chain, three_gauges, minter, token):
    assert token.balanceOf(accounts[0]) == 0
    minter.recover_balance(token, {"from": accounts[0]})
    assert token.balanceOf(accounts[0]) == 1_303_030_303 * 10 ** 18

def test_set_minter_admin_only(accounts, chain, three_gauges, minter, token):
    with brownie.reverts("dev: admin only"):
        minter.change_emergency_return(accounts[2], {"from": accounts[1]})
    with brownie.reverts("dev: admin only"):
        minter.change_admin(accounts[2], {"from": accounts[1]})
    with brownie.reverts("dev: admin only"):
        minter.commit_new_rate(100, {"from": accounts[1]})
    with brownie.reverts("dev: admin only"):
        minter.recover_balance(token, {"from": accounts[1]})

def test_prevent_fatfinger(accounts, chain, three_gauges, minter, token):
    with brownie.reverts("dev: preventing fatfinger"):
        minter.commit_new_rate(10_000_001, {"from": accounts[0]})
