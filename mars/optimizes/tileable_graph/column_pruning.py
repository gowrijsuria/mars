#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 1999-2020 Alibaba Group Holding Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ...compat import six
from ...utils import copy_tileables
from ...dataframe.groupby.aggregation import DataFrameGroupByAgg
from ...dataframe.datasource.read_csv import DataFrameReadCSV
from .core import TileableOptimizeRule, register


class GroupbyPruneReadCSV(TileableOptimizeRule):
    """
    An experimental implementation for tileable optimization rule.
    This rule works only when groupby aggregation operation follows the read CSV files,
    we can prune the columns that not used by the following operations when read the files.
    """
    def match(self, node):
        if isinstance(node.inputs[0].op, DataFrameReadCSV) and \
                node.inputs[0] not in self._optimizer_context.result_tileables:
            by_columns = node.op.by if isinstance(node.op.by, (list, tuple)) else [node.op.by]
            if isinstance(node.op.func, (six.string_types, list)):
                # Passing func name(s) means perform on all columns.
                return False
            elif len(set(by_columns + list(node.op.func))) == len(node.inputs[0].op.usecols or node.inputs[0].dtypes):
                # If performs on all columns, no need to prune.
                return False
            return True
        return False

    def apply(self, node):
        by_columns = node.op.by if isinstance(node.op.by, (list, tuple)) else [node.op.by]
        agg_columns = list(node.op.func)
        input_node = node.inputs[0]
        selected_columns = [c for c in list(input_node.dtypes.index) if c in by_columns + agg_columns]
        if input_node in self._optimizer_context:
            new_input = self._optimizer_context[input_node]
            selected_columns = [
                c for c in list(input_node.dtypes.index) if c in selected_columns + new_input.op._usecols]
        else:
            new_input = copy_tileables(input_node).data

        new_input._shape = (input_node.shape[0], len(selected_columns))
        new_input._dtypes = input_node.dtypes[selected_columns]
        new_input._columns_value = new_input._dtypes.index
        new_input.op._usecols = selected_columns
        new_node = copy_tileables(node, inputs=[new_input]).data

        self._optimizer_context[node] = new_node
        self._optimizer_context[input_node] = new_input
        return new_node


register(DataFrameGroupByAgg, GroupbyPruneReadCSV)
