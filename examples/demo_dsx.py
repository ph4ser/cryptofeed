'''
Copyright (C) 2017-2020  Bryant Moscon - bmoscon@gmail.com

Please see the LICENSE file for the terms and conditions
associated with this software.
'''
from cryptofeed.callback import TradeCallback, BookCallback
from cryptofeed import FeedHandler
from cryptofeed.exchanges import DSX
from cryptofeed.defines import L2_BOOK, BID, ASK, TRADES


async def trade(feed, pair, order_id, timestamp, side, amount, price, receipt_timestamp):
    print("Timestamp: {} Feed: {} Pair: {} ID: {} Side: {} Amount: {} Price: {}".format(timestamp, feed, pair, order_id, side, amount, price))


async def book(feed, pair, book, timestamp, receipt_timestamp):
    print('Timestamp: {} Feed: {} Pair: {} Book Bid Size is {} Ask Size is {}'.format(timestamp, feed, pair, len(book[BID]), len(book[ASK])))


def main():
    f = FeedHandler()

    f.add_feed(DSX(config={TRADES: ['BTC-USDT'], L2_BOOK: ['BTC-USDT']}, callbacks={TRADES: TradeCallback(trade), L2_BOOK: BookCallback(book)}))

    f.run()


if __name__ == '__main__':
    main()