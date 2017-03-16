# -*- coding: utf-8 -*-
#
# Copyright 2017 Ricequant, Inc
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import six

from .base_account import BaseAccount
from ...const import ACCOUNT_TYPE
from ...execution_context import ExecutionContext
from ...environment import Environment
from ...utils.i18n import gettext as _
from ...utils.logger import user_system_log


class FutureAccount(BaseAccount):
    def _get_starting_cash(self):
        return Environment.get_instance().config.base.future_starting_cash

    @property
    def type(self):
        return ACCOUNT_TYPE.FUTURE

    @staticmethod
    def _cal_frozen_cash(orders):
        frozen_cash = 0
        for order in orders:
            order_book_id = order.order_book_id
            instrument = ExecutionContext.get_instrument(order_book_id)
            value = order._frozen_price * order.unfilled_quantity * instrument.contract_multiplier
            frozen_cash += FutureAccount._cal_margin(order_book_id, value)
        return frozen_cash

    @staticmethod
    def _cal_margin(order_book_id, value):
        margin_rate = ExecutionContext.get_future_margin_rate(order_book_id)
        multiplier = Environment.get_instance().config.base.margin_multiplier
        return value * margin_rate * multiplier

    @property
    def cash(self):
        """
        [float] 可用资金
        """
        return self.total_value - self.margin - self.daily_holding_pnl - self.frozen_cash

    @property
    def total_value(self):
        return self._static_unit_net_value * self.units + self.daily_pnl

    @property
    def unit_net_value(self):
        return self.total_value / self.units

    # -- Margin 相关
    @property
    def margin(self):
        """
        [float] 总保证金
        """
        return sum(position.margin for position in six.itervalues(self.positions))

    def buy_margin(self):
        """
        [float] 买方向保证金
        """
        return sum(position.buy_margin for position in six.itervalues(self.positions))

    def sell_margin(self):
        """
        [float] 卖方向保证金
        """
        return sum(position.sell_margin for position in six.itervalues(self.positions))

    # -- PNL 相关
    @property
    def daily_pnl(self):
        """
        [float] 当日盈亏
        """
        return self.daily_realized_pnl + self.daily_holding_pnl - self.transaction_cost

    @property
    def daily_holding_pnl(self):
        """
        [float] 浮动盈亏
        """
        return sum(position.daily_holding_pnl for position in six.itervalues(self.positions))

    @property
    def daily_realized_pnl(self):
        """
        [float] 平仓盈亏
        """
        return sum(position.daily_realized_pnl for position in six.iteritems(self.positions))

    def bar(self, event):
        bar_dict = event.bar_dict
        for order_book_id, position in six.iteritems(self._positions):
            bar = bar_dict[order_book_id]
            if bar.isnan:
                continue
            position._last_price = bar.close

    def tick(self, event):
        tick = event.tick
        self.positions[tick.order_book_id].last_price = tick.last

    def settlement(self, event):
        for position in list(self.positions.values()):
            if position.is_de_listed():
                order_book_id = position.order_book_id
                user_system_log.warn(
                    _("{order_book_id} is expired, close all positions by system").format(order_book_id=order_book_id))
                self.positions.pop(order_book_id, None)
            elif position._quantity == 0:
                self.positions.pop(position.order_book_id, None)
            else:
                position.apply_settlement()

        self._static_unit_net_value = self.unit_net_value

    def order_pending_new(self, event):
        if self != event.account:
            return
        self._frozen_cash += self._cal_frozen_cash([event.order])

    def order_creation_reject(self, event):
        if self != event.account:
            return
        self._frozen_cash -= self._cal_frozen_cash([event.order])

    def order_cancellation_pass(self, event):
        if self != event.account:
            return
        self._frozen_cash -= self._cal_frozen_cash([event.order])

    def order_unsolicited_update(self, event):
        if self != event.account:
            return
        self._frozen_cash -= self._cal_frozen_cash([event.order])

    def trade(self, event):
        if self != event.account:
            return
        trade = event.trade
        order = trade.order
        order_book_id = order.order_book_id
        instrument = ExecutionContext.get_instrument(order_book_id)
        self._frozen_cash -= order._frozen_price * trade.last_quantity * instrument.contract_multiplier
        self._positions[order_book_id].apply_trade(trade)
















































