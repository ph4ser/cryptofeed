'''
Copyright (C) 2017-2021  Bryant Moscon - bmoscon@gmail.com

Please see the LICENSE file for the terms and conditions
associated with this software.
'''
import asyncio
import hashlib
import hmac
import time
from decimal import Decimal

from sortedcontainers import SortedDict as sd
from yapic import json

from cryptofeed.defines import BID, ASK, BUY, L2_BOOK, L3_BOOK, SELL, TICKER, TRADES
from cryptofeed.exchange import RestExchange


class BitfinexRestMixin(RestExchange):
    api = "https://api-pub.bitfinex.com/v2/"
    rest_channels = (
        TRADES, TICKER, L2_BOOK, L3_BOOK
    )

    def _nonce(self):
        return str(int(round(time.time() * 1000)))

    def _generate_signature(self, url: str, body=json.dumps({})):
        nonce = self._nonce()
        signature = "/api/" + url + nonce + body
        h = hmac.new(self.config.key_secret.encode('utf8'), signature.encode('utf8'), hashlib.sha384)
        signature = h.hexdigest()

        return {
            "bfx-nonce": nonce,
            "bfx-apikey": self.config.key_id,
            "bfx-signature": signature,
            "content-type": "application/json"
        }

    def _trade_normalization(self, symbol: str, trade: list) -> dict:
        if symbol[0] == 'f':
            # period is in days, from 2 to 30
            trade_id, timestamp, amount, price, period = trade
        else:
            trade_id, timestamp, amount, price = trade
            period = None

        ret = {
            'timestamp': self.timestamp_normalize(timestamp),
            'symbol': self.exchange_symbol_to_std_symbol(symbol),
            'id': trade_id,
            'feed': self.id,
            'side': SELL if amount < 0 else BUY,
            'amount': Decimal(abs(amount)),
            'price': Decimal(price),
        }

        if period:
            ret['period'] = period
        return ret

    def _dedupe(self, data, last):
        """
        Bitfinex does not support pagination, and using timestamps
        to paginate can lead to duplicate data being pulled
        """
        if len(last) == 0:
            return data

        ids = set([data[0] for data in last])
        ret = []

        for d in data:
            if d[0] in ids:
                continue
            ids.add(d[0])
            ret.append(d)

        return ret

    async def trades(self, symbol: str, start=None, end=None, retry_count=1, retry_delay=60):
        symbol = self.std_symbol_to_exchange_symbol(symbol)
        start, end = self._interval_normalize(start, end)
        start = int(start * 1000)
        end = int(end * 1000)
        last = []

        while True:
            endpoint = f"{self.api}trades/{symbol}/hist"
            if start and end:
                endpoint = f"{self.api}trades/{symbol}/hist?limit=5000&start={start}&end={end}&sort=1"

            r = await self.http_conn.read(endpoint, retry_count=retry_count, retry_delay=retry_delay)
            data = json.loads(r, parse_float=Decimal)

            if data:
                if data[-1][1] == start:
                    self.log.warning("%s: number of trades exceeds exchange time window, some data will not be retrieved for time %d", self.id, start)
                    start += 1
                else:
                    start = data[-1][1]

            orig_data = list(data)
            data = self._dedupe(data, last)
            last = list(orig_data)

            yield [self._trade_normalization(symbol, x) for x in data]

            if len(orig_data) < 5000:
                break
            await asyncio.sleep(1 / self.request_limit)

    async def ticker(self, symbol: str, retry_count=1, retry_delay=60):
        sym = self.std_symbol_to_exchange_symbol(symbol)
        r = await self.http_conn.read(f"{self.api}ticker/{sym}", retry_count=retry_count, retry_delay=retry_delay)
        data = json.loads(r, parse_float=Decimal)
        return {
            'symbol': symbol,
            'feed': self.id,
            'bid': Decimal(data[0]),
            'ask': Decimal(data[2])
        }

    async def l2_book(self, symbol: str, retry_count=0, retry_delay=60):
        return await self._rest_book(symbol, l3=False, retry_count=retry_count, retry_delay=retry_delay)

    async def l3_book(self, symbol: str, retry_count=0, retry_delay=60):
        return await self._rest_book(symbol, l3=True, retry_count=retry_count, retry_delay=retry_delay)

    async def _rest_book(self, symbol: str, l3=False, retry_count=0, retry_delay=60):
        symbol = self.std_symbol_to_exchange_symbol(symbol)
        ret = {BID: sd(), ASK: sd()}
        funding = 'f' in symbol

        precision = 'R0' if l3 is True else 'P0'
        r = await self.http_conn.read(f"{self.api}/book/{symbol}/{precision}?len=100", retry_delay=retry_delay, retry_count=retry_count)
        data = json.loads(r, parse_float=Decimal)

        if l3:
            for entry in data:
                if funding:
                    order_id, period, price, amount = entry
                    update = (abs(amount), period)
                else:
                    order_id, price, amount = entry
                    update = abs(amount)
                amount = Decimal(amount)
                price = Decimal(price)
                side = BID if (amount > 0 and not funding) or (amount < 0 and funding) else ASK
                if price not in ret[side]:
                    ret[side][price] = {order_id: update}
                else:
                    ret[side][price][order_id] = update
        else:
            for entry in data:
                if funding:
                    price, period, _, amount = entry
                    update = (abs(amount), period)
                else:
                    price, _, amount = entry
                    update = abs(amount)
                price = Decimal(price)
                amount = Decimal(amount)
                side = BID if (amount > 0 and not funding) or (amount < 0 and funding) else ASK
                ret[side][price] = update

        return ret