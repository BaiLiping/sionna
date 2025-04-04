#
# SPDX-FileCopyrightText: Copyright (c) 2021-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0#

import unittest
import numpy as np
import tensorflow as tf
from scipy.special import logsumexp
from sionna.phy import config
from sionna.phy.mapping import Constellation, Mapper, Demapper
from sionna.phy.mapping import SymbolDemapper
from sionna.phy.mapping import SymbolLogits2LLRs
from sionna.phy.mapping import SymbolLogits2Moments
from sionna.phy.mapping import LLRs2SymbolLogits
from sionna.phy.mapping import BinarySource
from sionna.phy.channel import AWGN
from scipy.special import softmax

class TestMapper(unittest.TestCase):

    def test_dimensions(self):
        num_bits_per_symbol = 4
        batch_size = 100
        num_symbols = 100
        binary_source = BinarySource()
        m = Mapper("qam", num_bits_per_symbol)

        x = m(binary_source([batch_size, num_symbols*num_bits_per_symbol]))
        self.assertEqual(x.shape, [batch_size, num_symbols])

        x = m(binary_source([batch_size,2,3,num_symbols*num_bits_per_symbol]))
        self.assertEqual(x.shape, [batch_size,2,3,num_symbols])

        x = m(binary_source([batch_size,2,3,num_symbols*num_bits_per_symbol]))
        self.assertEqual(x.shape, [batch_size,2,3,num_symbols])

    def test_mappings(self):
        num_bits_per_symbol = 8
        b = np.zeros([2**num_bits_per_symbol, num_bits_per_symbol])
        for i in range(0, 2**num_bits_per_symbol):
            b[i] = np.array(list(np.binary_repr(i,num_bits_per_symbol)), dtype=np.int32)
        m = Mapper("qam", num_bits_per_symbol)
        x = m(b)
        for i, s in enumerate(x.numpy()):
            self.assertEqual(s, m.constellation()[i])

    def test_graph_mode(self):
        binary_source = BinarySource()

        # simple precision

        mapper = Mapper("qam", 4)
        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            return mapper(b)
        self.assertEqual(run(100).shape, [100, 3, 100])
        self.assertEqual(run(400).shape, [400, 3, 100])

        # double precision

        mapper = Mapper("qam", 4, precision="double")
        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            return mapper(b)
        self.assertEqual(run(100).shape, [100, 3, 100])
        self.assertEqual(run(400).shape, [400, 3, 100])

    def test_graph_mode_jit(self):
        binary_source = BinarySource()

        # simple precision

        mapper = Mapper("qam", 4)
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            return mapper(b)
        self.assertEqual(run(100).shape, [100, 3, 100])
        self.assertEqual(run(400).shape, [400, 3, 100])

        # double precision

        mapper = Mapper("qam", 4, precision="double")
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            return mapper(b)
        self.assertEqual(run(100).shape, [100, 3, 100])
        self.assertEqual(run(400).shape, [400, 3, 100])

    def test_symbol_ind_output(self):
        binary_source = BinarySource()
        mapper = Mapper("qam", 4, return_indices=True)
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            return mapper(b)
        x, ind = run(100)
        self.assertEqual(x.shape, [100, 3, 100])
        self.assertEqual(ind.shape, [100, 3, 100])
        self.assertTrue(ind.dtype==tf.int32)

class TestDemapper(unittest.TestCase):
    def test_assert_demapping_method(self):
        c = Constellation("qam", 6)
        with self.assertRaises(AssertionError):
            Demapper("asdfiu", constellation=c)

    def test_assert_non_broadcastable_dimensions(self):
        points = config.tf_rng.normal([2**4])
        c = Constellation("custom", 4, points=points)
        m = Mapper(constellation=c)
        d = Demapper("app", constellation=c)
        b = config.tf_rng.uniform([100, 50, 200], minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([100, 50])
            llr = d(x, no)
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([100, 1])
            llr = d(x, no)

    def test_output_dimensions1(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            points = config.tf_rng.normal([2**num_bits_per_symbol])
            c = Constellation("custom", num_bits_per_symbol, points=points)
            m = Mapper(constellation=c)
            d = Demapper("app", constellation=c)
            batch_size = 99
            dim1 = 10
            dim2 = 12
            b = config.tf_rng.uniform([batch_size, dim1, dim2*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            llr = d(x, 1.)
            self.assertEqual(llr.shape, [batch_size, dim1, dim2*num_bits_per_symbol])

    def test_output_dimensions2(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            points = config.tf_rng.normal([2**num_bits_per_symbol])
            c = Constellation("custom", num_bits_per_symbol, points=points)
            m = Mapper(constellation=c)
            d = Demapper("app", constellation=c)
            batch_size = 99
            b = config.tf_rng.uniform([batch_size, num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            llr = d(x, 1.)
            self.assertEqual(llr.shape, [batch_size, num_bits_per_symbol])

    def test_no_inputs(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            points = config.tf_rng.normal([2**num_bits_per_symbol])
            c = Constellation("custom", num_bits_per_symbol, points=points)
            m = Mapper(constellation=c)
            d = Demapper("app", constellation=c)
            b = config.tf_rng.uniform([100, 10, 50*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            No = np.ones_like(x, dtype=np.float32)
            llr = d(x, No)
            self.assertEqual(llr.shape, [100, 10, 50*num_bits_per_symbol])

            No = np.ones_like(x, dtype=np.float32)
            llr = d(x, No)
            self.assertEqual(llr.shape, [100, 10, 50*num_bits_per_symbol])

            with self.assertRaises(tf.errors.InvalidArgumentError):
                d = Demapper("app", constellation=c)
                No = tf.constant(np.ones(x.shape[:-1]), dtype=tf.float32)
                llr = d(x, No)

    def test_per_symbol_noise_variance(self):
        "Test LLRs with per symbol noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        m = Mapper("qam", num_bits_per_symbol)
        d_app = Demapper("app", "qam", num_bits_per_symbol)
        d_maxlog = Demapper("maxlog", "qam", num_bits_per_symbol)
        b = config.tf_rng.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = config.tf_rng.uniform(x.shape, minval=0.01, maxval=100, dtype=np.float32)
        llr_app = d_app(x, No)
        llr_maxlog = d_maxlog(x, No)
        p = d_app.constellation.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - p)**2
                exp = -dist/No[l,i]

                llrnp_app = logsumexp(np.take(exp, d_app._logits2llrs._c1),axis=0) - logsumexp(np.take(exp, d_app._logits2llrs._c0),axis=0)
                llrtarget_app = llr_app[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_app, llrtarget_app, atol=1e-5))

                llrnp_maxlog = np.max(np.take(exp, d_maxlog._logits2llrs._c1),axis=0) - np.max(np.take(exp, d_maxlog._logits2llrs._c0),axis=0)
                llrtarget_maxlog = llr_maxlog[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_maxlog, llrtarget_maxlog, atol=1e-5))

    def test_broadcastable_noise_variance(self):
        "Test LLRs with broadcastable noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        m = Mapper("qam", num_bits_per_symbol)
        d_app = Demapper("app", "qam", num_bits_per_symbol)
        d_maxlog = Demapper("maxlog", "qam", num_bits_per_symbol)
        b = config.tf_rng.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = config.tf_rng.uniform([1, 10], minval=0.01, maxval=100, dtype=np.float32)
        llr_app = d_app(x, No)
        llr_maxlog = d_maxlog(x, No)
        p = m.constellation.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - p)**2
                exp = -dist/No[0,i]

                llrnp_app = logsumexp(np.take(exp, d_app._logits2llrs._c1),axis=0) - logsumexp(np.take(exp, d_app._logits2llrs._c0),axis=0)
                llrtarget_app = llr_app[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_app, llrtarget_app, atol=1e-5))

                llrnp_maxlog = np.max(np.take(exp, d_maxlog._logits2llrs._c1),axis=0) - np.max(np.take(exp, d_maxlog._logits2llrs._c0),axis=0)
                llrtarget_maxlog = llr_maxlog[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_maxlog, llrtarget_maxlog, atol=1e-5))

    def test_graph_mode(self):
        binary_source = BinarySource()

        # simple precision

        constellation = Constellation("qam", 4)
        mapper = Mapper(constellation=constellation)
        awgn = AWGN()
        demapper = Demapper("app", constellation=constellation)
        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float32)
            y = awgn(x, no)
            return demapper(y, no)
        self.assertEqual(run(100).shape, [100, 3, 400])
        self.assertEqual(run(400).shape, [400, 3, 400])

        # double precision

        constellation = Constellation("qam", 4, precision="double")
        mapper = Mapper(constellation=constellation, precision="double")
        awgn = AWGN(precision="double")
        demapper = Demapper("app", constellation=constellation, precision="double")
        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float64)
            y = awgn(x, no)
            return demapper(y, no)
        self.assertEqual(run(100).shape, [100, 3, 400])
        self.assertEqual(run(400).shape, [400, 3, 400])

    def test_graph_mode_jit(self):
        binary_source = BinarySource()

        # simple precision

        constellation = Constellation("qam", 4)
        mapper = Mapper(constellation=constellation)
        awgn = AWGN()
        demapper = Demapper("app", constellation=constellation)
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float32)
            y = awgn(x, no)
            return demapper(y, no)
        self.assertEqual(run(100).shape, [100, 3, 400])
        self.assertEqual(run(400).shape, [400, 3, 400])

        # double precision

        constellation = Constellation("qam", 4, precision="double")
        mapper = Mapper(constellation=constellation, precision="double")
        awgn = AWGN(precision="double")
        demapper = Demapper("app", constellation=constellation, precision="double")
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float64)
            y = awgn(x, no)
            return demapper(y, no)
        self.assertEqual(run(100).shape, [100, 3, 400])
        self.assertEqual(run(400).shape, [400, 3, 400])

class TestDemapperWithPrior(unittest.TestCase):
    def test_assert_demapping_method(self):
        c = Constellation("qam", 6)
        with self.assertRaises(AssertionError):
            Demapper("asdfiu", constellation=c, with_prior=True)

    def test_assert_non_broadcastable_dimensions(self):
        num_bits_per_symbol = 4
        points = config.tf_rng.normal([2**num_bits_per_symbol])
        c = Constellation("custom", num_bits_per_symbol, points=points)
        m = Mapper(constellation=c)
        d = Demapper("app", constellation=c, with_prior=True)
        b = config.tf_rng.uniform([16, 50, 200], minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        # Noise
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([16, 50])
            p = config.tf_rng.uniform([4])
            llr = d(x, no, p)
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([16, 1])
            p = config.tf_rng.uniform([4])
            llr = d(x, no, p)
        # prior
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = config.tf_rng.uniform([16, 50, 4])
            llr = d(x, 1.0, p)
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = config.tf_rng.uniform([16, 50, 200])
            llr = d(x, 1.0, p)
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = config.tf_rng.uniform([16, 1])
            llr = d(x, 1.0, p)

    def test_output_dimensions1(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            points = config.tf_rng.normal([2**num_bits_per_symbol])
            c = Constellation("custom", num_bits_per_symbol, points=points)
            m = Mapper(constellation=c)
            d = Demapper("app", constellation=c, with_prior=True)
            batch_size = 99
            dim1 = 10
            dim2 = 12
            b = config.tf_rng.uniform([batch_size, dim1, dim2*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            p = config.tf_rng.uniform([num_bits_per_symbol])
            llr = d(x, 1., p)
            self.assertEqual(llr.shape, [batch_size, dim1, dim2*num_bits_per_symbol])

    def test_output_dimensions2(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            points = config.tf_rng.normal([2**num_bits_per_symbol])
            c = Constellation("custom", num_bits_per_symbol, points=points)
            m = Mapper(constellation=c)
            d = Demapper("app", constellation=c, with_prior=True)
            batch_size = 99
            b = config.tf_rng.uniform([batch_size, num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            p = config.tf_rng.uniform([num_bits_per_symbol])
            llr = d(x, 1., p)
            self.assertEqual(llr.shape, [batch_size, num_bits_per_symbol])

    def test_no_inputs(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            points = config.tf_rng.normal([2**num_bits_per_symbol])
            c = Constellation("custom", num_bits_per_symbol, points=points)
            m = Mapper(constellation=c)
            d = Demapper("app", constellation=c, with_prior=True)
            b = config.tf_rng.uniform([100, 10, 50*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            No = np.ones_like(x, dtype=np.float32)
            p = config.tf_rng.uniform([num_bits_per_symbol])
            llr = d(x, No, p)
            self.assertEqual(llr.shape, [100, 10, 50*num_bits_per_symbol])

            with self.assertRaises(tf.errors.InvalidArgumentError):
                No = tf.constant(np.ones(x.shape[:-1]), dtype=tf.float32)
                p = config.tf_rng.uniform([num_bits_per_symbol])
                llr = d(x, No, p)

    def test_prior_inputs(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            points = config.tf_rng.normal([2**num_bits_per_symbol])
            c = Constellation("custom", num_bits_per_symbol, points=points)
            m = Mapper(constellation=c)
            d = Demapper("app", constellation=c, with_prior=True)
            b = config.tf_rng.uniform([100, 10, 50*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            No = np.ones_like(x, dtype=np.float32)
            p = config.tf_rng.uniform([100, 10, 50, num_bits_per_symbol])
            llr = d(x, No, p)
            self.assertEqual(llr.shape, [100, 10, 50*num_bits_per_symbol])

            with self.assertRaises(tf.errors.InvalidArgumentError):
                p = config.tf_rng.uniform([100, 10, 49, num_bits_per_symbol])
                llr = d(x, No, p)

    def test_per_symbol_noise_variance_and_prior(self):
        "Test LLRs with per symbol noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        num_points = 2**num_bits_per_symbol
        m = Mapper("qam", num_bits_per_symbol)
        d_app = Demapper("app", "qam", num_bits_per_symbol, with_prior=True)
        d_maxlog = Demapper("maxlog", "qam", num_bits_per_symbol, with_prior=True)
        b = config.tf_rng.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = config.tf_rng.uniform(x.shape, minval=0.01, maxval=100, dtype=np.float32)
        # Precompute priors and probabilities on symbols
        prior = config.tf_rng.normal(tf.concat([x.shape, [num_bits_per_symbol]], axis=0))
        a = np.zeros([num_points, num_bits_per_symbol])
        for i in range(0, num_points):
            a[i,:] = np.array(list(np.binary_repr(i, num_bits_per_symbol)),
                              dtype=np.int32)
        a = 2*a-1
        a = np.expand_dims(a, axis=(0, 1))
        ps_exp = a*np.expand_dims(prior, axis=-2)
        ps_exp = ps_exp - np.log(1+np.exp(ps_exp)) # log(sigmoid(ps_exp))
        ps_exp = np.sum(ps_exp, axis=-1) # [batch size, block length, num points]
        #
        llr_app = d_app(x, No, prior)
        llr_maxlog = d_maxlog(x, No, prior)
        p = d_app.constellation.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - p)**2
                exp = -dist/No[l,i]
                ps_exp_ = ps_exp[l,i]

                llrnp_app = logsumexp(np.take(exp, d_app._logits2llrs._c1) + np.take(ps_exp_, d_app._logits2llrs._c1),axis=0)\
                    - logsumexp(np.take(exp, d_app._logits2llrs._c0) + np.take(ps_exp_, d_app._logits2llrs._c0),axis=0)
                llrtarget_app = llr_app[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_app, llrtarget_app, atol=1e-5))

                llrnp_maxlog = np.max(np.take(exp, d_maxlog._logits2llrs._c1) + np.take(ps_exp_, d_app._logits2llrs._c1),axis=0)\
                    - np.max(np.take(exp, d_maxlog._logits2llrs._c0) + np.take(ps_exp_, d_app._logits2llrs._c0),axis=0)
                llrtarget_maxlog = llr_maxlog[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_maxlog, llrtarget_maxlog, atol=1e-5))

    def test_broadcastable_noise_variance_and_prior(self):
        "Test LLRs with broadcastable noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        num_points = 2**num_bits_per_symbol
        m = Mapper("qam", num_bits_per_symbol)
        d_app = Demapper("app", "qam", num_bits_per_symbol, with_prior=True)
        d_maxlog = Demapper("maxlog", "qam", num_bits_per_symbol, with_prior=True)
        b = config.tf_rng.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = config.tf_rng.uniform([1, 10], minval=0.01, maxval=100, dtype=np.float32)
        # Precompute priors and probabilities on symbols
        prior = config.tf_rng.normal([num_bits_per_symbol])
        a = np.zeros([num_points, num_bits_per_symbol])
        for i in range(0, num_points):
            a[i,:] = np.array(list(np.binary_repr(i, num_bits_per_symbol)),
                              dtype=np.int32)
        a = 2*a-1
        ps_exp = a*np.expand_dims(prior, axis=0)
        ps_exp = ps_exp - np.log(1+np.exp(ps_exp)) # log(sigmoid(ps_exp))
        ps_exp = np.sum(ps_exp, axis=-1) # [num points]
        #
        llr_app = d_app(x, No, prior)
        llr_maxlog = d_maxlog(x, No, prior)
        p = m.constellation.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - p)**2
                exp = -dist/No[0,i]

                llrnp_app = logsumexp(np.take(exp, d_app._logits2llrs._c1) + np.take(ps_exp, d_app._logits2llrs._c1),axis=0)\
                    - logsumexp(np.take(exp, d_app._logits2llrs._c0) + np.take(ps_exp, d_app._logits2llrs._c0),axis=0)
                llrtarget_app = llr_app[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_app, llrtarget_app, atol=1e-5))

                llrnp_maxlog = np.max(np.take(exp, d_maxlog._logits2llrs._c1) + np.take(ps_exp, d_app._logits2llrs._c1),axis=0)\
                    - np.max(np.take(exp, d_maxlog._logits2llrs._c0) + np.take(ps_exp, d_app._logits2llrs._c0),axis=0)
                llrtarget_maxlog = llr_maxlog[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_maxlog, llrtarget_maxlog, atol=1e-5))

    def test_graph_mode(self):
        binary_source = BinarySource()

        # simple precision

        constellation = Constellation("qam", 4)
        mapper = Mapper(constellation=constellation)
        awgn = AWGN()
        demapper = Demapper("app", constellation=constellation, with_prior=True)
        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float32)
            prior = config.tf_rng.normal([4])
            y = awgn(x, no)
            return demapper(y, no, prior)
        self.assertEqual(run(100).shape, [100, 3, 400])
        self.assertEqual(run(400).shape, [400, 3, 400])

        # double precision

        constellation = Constellation("qam", 4, precision="double")
        mapper = Mapper(constellation=constellation, precision="double")
        awgn = AWGN(precision="double")
        demapper = Demapper("app", constellation=constellation, with_prior=True, precision="double")
        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float64)
            prior = config.tf_rng.normal([4], dtype=tf.float64)
            y = awgn(x, no)
            return demapper(y, no, prior)
        self.assertEqual(run(100).shape, [100, 3, 400])
        self.assertEqual(run(400).shape, [400, 3, 400])

    def test_graph_mode_jit(self):
        binary_source = BinarySource()

        # simple precision

        constellation = Constellation("qam", 4)
        mapper = Mapper(constellation=constellation)
        awgn = AWGN()
        demapper = Demapper("app", constellation=constellation, with_prior=True)
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float32)
            prior = config.tf_rng.normal([4])
            y = awgn(x, no)
            return demapper(y, no, prior)
        self.assertEqual(run(100).shape, [100, 3, 400])
        self.assertEqual(run(400).shape, [400, 3, 400])

        # double precision

        constellation = Constellation("qam", 4, precision="double")
        mapper = Mapper(constellation=constellation, precision="double")
        awgn = AWGN(precision="double")
        demapper = Demapper("app", constellation=constellation, with_prior=True, precision="double")
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float64)
            prior = config.tf_rng.normal([4], dtype=tf.float64)
            y = awgn(x, no)
            return demapper(y, no, prior)
        self.assertEqual(run(100).shape, [100, 3, 400])
        self.assertEqual(run(400).shape, [400, 3, 400])

class TestSymbolDemapperWithPrior(unittest.TestCase):

    def test_assert_non_broadcastable_dimensions(self):
        num_bits_per_symbol = 4
        points = config.tf_rng.normal([2**num_bits_per_symbol])
        c = Constellation("custom", num_bits_per_symbol, points=points)
        m = Mapper(constellation=c)
        d = SymbolDemapper(constellation=c, with_prior=True)
        b = config.tf_rng.uniform([64, 10, 200], minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        # Noise
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([64, 9])
            p = config.tf_rng.uniform([16])
            logits = d(x, no, p)
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([32, 10])
            p = config.tf_rng.uniform([16])
            logits = d(x, no, p)
        # prior
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = config.tf_rng.uniform([64, 10, 16])
            logits = d(x, 1., p)
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = config.tf_rng.uniform([64, 10, 50])
            logits = d(x, 1., p)
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = config.tf_rng.uniform([64])
            logits = d(x, 1., p)

    def test_output_dimensions1(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            num_points = 2**num_bits_per_symbol
            points = config.tf_rng.normal([num_points])
            c = Constellation("custom", num_bits_per_symbol, points=points)
            m = Mapper(constellation=c)
            d = SymbolDemapper(constellation=c, with_prior=True)
            batch_size = 32
            dim1 = 10
            dim2 = 12
            b = config.tf_rng.uniform([batch_size, dim1, dim2*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            p = config.tf_rng.uniform([num_points])
            logits = d(x, 1., p)
            self.assertEqual(logits.shape, [batch_size, dim1, dim2, num_points])

    def test_output_dimensions2(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            num_points = 2**num_bits_per_symbol
            points = config.tf_rng.normal([num_points])
            c = Constellation("custom", num_bits_per_symbol, points=points)
            m = Mapper(constellation=c)
            d = SymbolDemapper(constellation=c, with_prior=True)
            batch_size = 32
            b = config.tf_rng.uniform([batch_size, num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            p = config.tf_rng.uniform([num_points])
            logits = d(x, 1., p)
            self.assertEqual(logits.shape, [batch_size, 1, num_points])

    def test_no_inputs(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            num_points = 2**num_bits_per_symbol
            points = config.tf_rng.normal([num_points])
            c = Constellation("custom", num_bits_per_symbol, points=points)
            m = Mapper(constellation=c)
            d = SymbolDemapper(constellation=c, with_prior=True)
            b = config.tf_rng.uniform([100, 10, 50*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            No = np.ones_like(x, dtype=np.float32)
            p = config.tf_rng.uniform([num_points])
            logits = d(x, No, p)
            self.assertEqual(logits.shape, [100, 10, 50, num_points])

            with self.assertRaises(tf.errors.InvalidArgumentError):
                No = tf.constant(np.ones(x.shape[1:]), dtype=tf.float32)
                p = config.tf_rng.uniform([num_points])
                logits = d(x, No, p)

    def test_prior_inputs(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            num_points = 2**num_bits_per_symbol
            points = config.tf_rng.normal([num_points])
            c = Constellation("custom", num_bits_per_symbol, points=points)
            m = Mapper(constellation=c)
            d = SymbolDemapper(constellation=c, with_prior=True)
            b = config.tf_rng.uniform([100, 10, 50*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            No = np.ones_like(x, dtype=np.float32)
            p = config.tf_rng.uniform([100, 10, 50, num_points])
            logits = d(x, No, p)
            self.assertEqual(logits.shape, [100, 10, 50, num_points])

            with self.assertRaises(tf.errors.InvalidArgumentError):
                p = config.tf_rng.uniform([100, 10, 49, num_points])
                logits = d(x, No, p)

    def test_per_symbol_noise_variance_and_prior(self):
        "Test LLRs with per symbol noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        num_points = 2**num_bits_per_symbol
        c = Constellation("qam", num_bits_per_symbol)
        m = Mapper(constellation=c)
        d = SymbolDemapper(constellation=c, with_prior=True)
        b = config.tf_rng.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = config.tf_rng.uniform(x.shape, minval=0.01, maxval=100, dtype=np.float32)
        # Precompute priors and probabilities on symbols
        prior = config.tf_rng.normal(tf.concat([x.shape, [num_points]], axis=0))
        #
        logits = d(x, No, prior)
        points = c.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - points)**2
                exp = -dist/No[l,i]

                logits_ref = exp + prior[l,i]
                logits_ref = logits_ref.numpy()
                logits_ref = logits_ref - np.log(np.sum(np.exp(logits_ref)))  # log(sigmoid(.))
                logits_target = logits[l,i].numpy()
                self.assertTrue(np.allclose(logits_ref, logits_target, atol=1e-5))

    def test_broadcastable_noise_variance_and_prior(self):
        "Test LLRs with broadcastable noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        num_points = 2**num_bits_per_symbol
        c = Constellation("qam", num_bits_per_symbol)
        m = Mapper(constellation=c)
        d = SymbolDemapper(constellation=c, with_prior=True)
        b = config.tf_rng.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = config.tf_rng.uniform([1, 10], minval=0.01, maxval=100, dtype=np.float32)
        # Precompute priors and probabilities on symbols
        prior = config.tf_rng.normal([num_points])
        #
        logits = d(x, No, prior)
        points = m.constellation.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - points)**2
                exp = -dist/No[0,i]

                logits_ref = exp + prior
                logits_ref = logits_ref.numpy()
                logits_ref = logits_ref - np.log(np.sum(np.exp(logits_ref)))  # log(sigmoid(.))
                logits_target = logits[l,i].numpy()
                self.assertTrue(np.allclose(logits_ref, logits_target, atol=1e-5))

    def test_graph_mode(self):
        num_bits_per_symbol = 4
        num_points = 2**num_bits_per_symbol
        binary_source = BinarySource()

        # simple precision

        c = Constellation("qam", num_bits_per_symbol)
        mapper = Mapper(constellation=c)
        awgn = AWGN()
        demapper = SymbolDemapper(constellation=c, with_prior=True)

        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float32)
            prior = config.tf_rng.normal([num_points], dtype=tf.float32)
            y = awgn(x, no)
            return demapper(x, no, prior)
        self.assertEqual(run(100).shape, [100, 3, 100, 16])
        self.assertEqual(run(400).shape, [400, 3, 100, 16])

        # double precision
        c = Constellation("qam", num_bits_per_symbol, precision="double")
        mapper = Mapper(constellation=c, precision="double")
        awgn = AWGN(precision="double")
        demapper = SymbolDemapper(constellation=c, with_prior=True, precision="double")
        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float64)
            prior = config.tf_rng.normal([num_points], dtype=tf.float64)
            y = awgn(x, no)
            return demapper(x, no, prior)
        self.assertEqual(run(100).shape, [100, 3, 100, 16])
        self.assertEqual(run(400).shape, [400, 3, 100, 16])

    def test_graph_mode_jit(self):
        num_bits_per_symbol = 4
        num_points = 2**num_bits_per_symbol
        binary_source = BinarySource()

        # simple precision

        c = Constellation("qam", num_bits_per_symbol)
        mapper = Mapper(constellation=c)
        awgn = AWGN()
        demapper = SymbolDemapper(constellation=c, with_prior=True)
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float32)
            prior = config.tf_rng.normal([num_points], dtype=tf.float32)
            y = awgn(x, no)
            return demapper(x, no, prior)
        self.assertEqual(run(100).shape, [100, 3, 100, 16])
        self.assertEqual(run(400).shape, [400, 3, 100, 16])

        # double precision

        c = Constellation("qam", num_bits_per_symbol, precision="double")
        mapper = Mapper(constellation=c, precision="double")
        awgn = AWGN(precision="double")
        demapper = SymbolDemapper(constellation=c, with_prior=True, precision="double")
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float64)
            prior = config.tf_rng.normal([num_points], dtype=tf.float64)
            y = awgn(x, no)
            return demapper(x, no, prior)
        self.assertEqual(run(100).shape, [100, 3, 100, 16])
        self.assertEqual(run(400).shape, [400, 3, 100, 16])

class TestSymbolDemapper(unittest.TestCase):

    def test_assert_non_broadcastable_dimensions(self):
        num_bits_per_symbol = 4
        points = config.tf_rng.normal([2**num_bits_per_symbol])
        c = Constellation("custom", num_bits_per_symbol, points=points)
        m = Mapper(constellation=c)
        d = SymbolDemapper(constellation=c)
        b = config.tf_rng.uniform([64, 10, 200], minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        # Noise
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([64, 9])
            logits = d(x, no)
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([32, 10])
            p = config.tf_rng.uniform([16])
            logits = d(x, no)

    def test_output_dimensions1(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            num_points = 2**num_bits_per_symbol
            points = config.tf_rng.normal([num_points])
            c = Constellation("custom", num_bits_per_symbol, points=points)
            m = Mapper(constellation=c)
            d = SymbolDemapper(constellation=c)
            batch_size = 32
            dim1 = 10
            dim2 = 12
            b = config.tf_rng.uniform([batch_size, dim1, dim2*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            logits = d(x, 1.)
            self.assertEqual(logits.shape, [batch_size, dim1, dim2, num_points])

    def test_output_dimensions2(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            num_points = 2**num_bits_per_symbol
            points = config.tf_rng.normal([num_points])
            c = Constellation("custom", num_bits_per_symbol, points=points)
            m = Mapper(constellation=c)
            d = SymbolDemapper(constellation=c)
            batch_size = 32
            b = config.tf_rng.uniform([batch_size, num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            logits = d(x, 1.)
            self.assertEqual(logits.shape, [batch_size, 1, num_points])

    def test_no_inputs(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            num_points = 2**num_bits_per_symbol
            points = config.tf_rng.normal([num_points])
            c = Constellation("custom", num_bits_per_symbol, points=points)
            m = Mapper(constellation=c)
            d = SymbolDemapper(constellation=c)
            b = config.tf_rng.uniform([100, 10, 50*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            No = np.ones_like(x, dtype=np.float32)
            logits = d(x, No)
            self.assertEqual(logits.shape, [100, 10, 50, num_points])

            with self.assertRaises(tf.errors.InvalidArgumentError):
                No = tf.constant(np.ones(x.shape[1:]), dtype=tf.float32)
                logits = d(x, No)

    def test_per_symbol_noise_variance(self):
        "Test LLRs with per symbol noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        c = Constellation("qam", num_bits_per_symbol)
        m = Mapper(constellation=c)
        d = SymbolDemapper(constellation=c)
        b = config.tf_rng.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = config.tf_rng.uniform(x.shape, minval=0.01, maxval=100, dtype=np.float32)
        #
        logits = d(x, No)
        points = c.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - points)**2
                exp = -dist/No[l,i]

                logits_ref = exp.numpy()
                logits_ref = logits_ref - np.log(np.sum(np.exp(logits_ref))) # log(sigmoid(.))
                logits_target = logits[l,i].numpy()
                self.assertTrue(np.allclose(logits_ref, logits_target, atol=1e-5))

    def test_broadcastable_noise_variance(self):
        "Test LLRs with broadcastable noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        c = Constellation("qam", num_bits_per_symbol)
        m = Mapper(constellation=c)
        d = SymbolDemapper(constellation=c)
        b = config.tf_rng.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = config.tf_rng.uniform([1, 10], minval=0.01, maxval=100, dtype=np.float32)
        #
        logits = d(x, No)
        points = m.constellation.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - points)**2
                exp = -dist/No[0,i]

                logits_ref = exp.numpy()
                logits_ref = logits_ref - np.log(np.sum(np.exp(logits_ref)))  # log(sigmoid(.))
                logits_target = logits[l,i].numpy()
                self.assertTrue(np.allclose(logits_ref, logits_target, atol=1e-5))

    def test_graph_mode(self):
        num_bits_per_symbol = 4
        binary_source = BinarySource()

        # simple precision

        c = Constellation("qam", num_bits_per_symbol, precision="single")
        mapper = Mapper(constellation=c, precision="single")
        awgn = AWGN(precision="single")
        demapper = SymbolDemapper(constellation=c, precision="single")
        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float32)
            y = awgn(x, no)
            return demapper(y, no)
        self.assertEqual(run(100).shape, [100, 3, 100, 16])
        self.assertEqual(run(400).shape, [400, 3, 100, 16])

        # double precision

        c = Constellation("qam", num_bits_per_symbol, precision="double")
        mapper = Mapper(constellation=c, precision="double")
        awgn = AWGN(precision="double")
        demapper = SymbolDemapper(constellation=c, precision="double")
        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float64)
            y = awgn(x, no)
            return demapper(y, no)
        self.assertEqual(run(100).shape, [100, 3, 100, 16])
        self.assertEqual(run(400).shape, [400, 3, 100, 16])

    def test_graph_mode_jit(self):
        num_bits_per_symbol = 4
        binary_source = BinarySource()

        # simple precision

        c = Constellation("qam", num_bits_per_symbol, precision="single")
        mapper = Mapper(constellation=c, precision="single")
        awgn = AWGN(precision="single")
        demapper = SymbolDemapper(constellation=c, precision="single")
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float32)
            y = awgn(x, no)
            return demapper(y, no)
        self.assertEqual(run(100).shape, [100, 3, 100, 16])
        self.assertEqual(run(400).shape, [400, 3, 100, 16])

        # double precision

        c = Constellation("qam", num_bits_per_symbol, precision="double")
        mapper = Mapper(constellation=c, precision="double")
        awgn = AWGN(precision="double")
        demapper = SymbolDemapper(constellation=c, precision="double")
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = config.tf_rng.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=tf.float64)
            y = awgn(x, no)
            return demapper(y, no)
        self.assertEqual(run(100).shape, [100, 3, 100, 16])
        self.assertEqual(run(400).shape, [400, 3, 100, 16])

class TestSymbolLogits2LLRsWithPrior(unittest.TestCase):
    def test_assert_demapping_method(self):
        with self.assertRaises(AssertionError):
            SymbolLogits2LLRs("asdfiu", 6)

    def test_assert_non_broadcastable_dimensions(self):
        d = SymbolLogits2LLRs("app", 4, with_prior=True)
        l = config.tf_rng.uniform([16, 50, 200, 16], minval=-20., maxval=20., dtype=tf.dtypes.float32)
        # prior
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = config.tf_rng.uniform([16, 50, 4])
            llr = d(l, p)
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = config.tf_rng.uniform([16, 50, 200])
            llr = d(l, p)
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = config.tf_rng.uniform([16, 1])
            llr = d(l, p)

    def test_output_dimensions1(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            d = SymbolLogits2LLRs("app", num_bits_per_symbol, with_prior=True)
            batch_size = 99
            dim1 = 10
            dim2 = 12
            l = config.tf_rng.uniform([batch_size, dim1, dim2, 2**num_bits_per_symbol],
                                minval=-20.0, maxval=20.0, dtype=tf.dtypes.float32)
            p = config.tf_rng.uniform([num_bits_per_symbol])
            llr = d(l, p)
            self.assertEqual(llr.shape, [batch_size, dim1, dim2, num_bits_per_symbol])

    def test_output_dimensions2(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            d = SymbolLogits2LLRs("app", num_bits_per_symbol, with_prior=True)
            batch_size = 99
            l = config.tf_rng.uniform([batch_size, 2**num_bits_per_symbol],
                                minval=-20.0, maxval=20.0, dtype=tf.dtypes.float32)
            p = config.tf_rng.uniform([num_bits_per_symbol])
            llr = d(l, p)
            self.assertEqual(llr.shape, [batch_size, num_bits_per_symbol])

    def test_prior_inputs(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            d = SymbolLogits2LLRs("app", num_bits_per_symbol, with_prior=True)
            l = config.tf_rng.uniform([100, 10, 50, 2**num_bits_per_symbol],
                                minval=-20.0, maxval=20.0, dtype=tf.dtypes.float32)
            p = config.tf_rng.uniform([100, 10, 50, num_bits_per_symbol])
            llr = d(l, p)
            self.assertEqual(llr.shape, [100, 10, 50, num_bits_per_symbol])

            with self.assertRaises(tf.errors.InvalidArgumentError):
                p = config.tf_rng.uniform([100, 10, 49, num_bits_per_symbol])
                llr = d(l, p)

    def test_llr_calc(self):
        "Test LLRs computation APP/MAXLOG"
        num_bits_per_symbol = 6
        num_points = 2**num_bits_per_symbol
        d_app = SymbolLogits2LLRs("app", num_bits_per_symbol, with_prior=True)
        d_maxlog = SymbolLogits2LLRs("maxlog", num_bits_per_symbol, with_prior=True)
        logits = config.tf_rng.uniform([100, 10, num_points],
                                        minval=-20.0, maxval=20.0, dtype=tf.dtypes.float32)
        # Precompute priors and probabilities on symbols
        prior = config.tf_rng.normal(tf.concat([logits.shape[:-1], [num_bits_per_symbol]], axis=0))
        a = np.zeros([num_points, num_bits_per_symbol])
        for i in range(0, num_points):
            a[i,:] = np.array(list(np.binary_repr(i, num_bits_per_symbol)),
                              dtype=np.int32)
        a = 2*a-1
        a = np.expand_dims(a, axis=(0, 1))
        ps_exp = a*np.expand_dims(prior, axis=-2)
        ps_exp = ps_exp - np.log(1+np.exp(ps_exp)) # log(sigmoid(ps_exp))
        ps_exp = np.sum(ps_exp, axis=-1) # [batch size, block length, num points]
        #
        llr_app = d_app(logits, prior)
        llr_maxlog = d_maxlog(logits, prior)
        for b in range(0, logits.shape[0]):
            for i in range(0, logits.shape[1]):
                ps_exp_ = ps_exp[b,i]

                llrnp_app = logsumexp(np.take(logits[b,i], d_app._c1) + np.take(ps_exp_, d_app._c1),axis=0)\
                    - logsumexp(np.take(logits[b,i], d_app._c0) + np.take(ps_exp_, d_app._c0),axis=0)
                llrtarget_app = llr_app[b,i].numpy()
                self.assertTrue(np.allclose(llrnp_app, llrtarget_app, atol=1e-5))

                llrnp_maxlog = np.max(np.take(logits[b,i], d_maxlog._c1) + np.take(ps_exp_, d_app._c1),axis=0)\
                    - np.max(np.take(logits[b,i], d_maxlog._c0) + np.take(ps_exp_, d_app._c0),axis=0)
                llrtarget_maxlog = llr_maxlog[b,i].numpy()
                self.assertTrue(np.allclose(llrnp_maxlog, llrtarget_maxlog, atol=1e-5))

    def test_graph_mode(self):
        num_bits_per_symbol = 4

        # simple precision

        l2l = SymbolLogits2LLRs("app", num_bits_per_symbol, with_prior=True)
        @tf.function
        def run(batch_size):
            logits = config.tf_rng.normal([batch_size, 150, 2**num_bits_per_symbol])
            prior = config.tf_rng.normal([num_bits_per_symbol])
            return l2l(logits, prior)
        self.assertEqual(run(100).shape, [100, 150, num_bits_per_symbol])
        self.assertEqual(run(400).shape, [400, 150, num_bits_per_symbol])

        # double precision

        l2l = SymbolLogits2LLRs("app", num_bits_per_symbol, with_prior=True, precision="double")
        @tf.function
        def run(batch_size):
            logits = config.tf_rng.normal([batch_size, 150, 2**num_bits_per_symbol])
            prior = config.tf_rng.normal([num_bits_per_symbol])
            return l2l(logits, prior)
        self.assertEqual(run(100).shape, [100, 150, num_bits_per_symbol])
        self.assertEqual(run(400).shape, [400, 150, num_bits_per_symbol])

    def test_graph_mode_jit(self):
        num_bits_per_symbol = 4

        # simple precision

        l2l = SymbolLogits2LLRs("app", num_bits_per_symbol, with_prior=True)
        @tf.function(jit_compile=True)
        def run(batch_size):
            logits = config.tf_rng.normal([batch_size, 150, 2**num_bits_per_symbol])
            prior = config.tf_rng.normal([num_bits_per_symbol])
            return l2l(logits, prior)
        self.assertEqual(run(100).shape, [100, 150, num_bits_per_symbol])
        self.assertEqual(run(400).shape, [400, 150, num_bits_per_symbol])

        # double precision

        l2l = SymbolLogits2LLRs("app", num_bits_per_symbol, with_prior=True, precision="double")
        @tf.function(jit_compile=True)
        def run(batch_size):
            logits = config.tf_rng.normal([batch_size, 150, 2**num_bits_per_symbol])
            prior = config.tf_rng.normal([num_bits_per_symbol])
            return l2l(logits, prior)
        self.assertEqual(run(100).shape, [100, 150, num_bits_per_symbol])
        self.assertEqual(run(400).shape, [400, 150, num_bits_per_symbol])

class TestSymbolLogits2LLRs(unittest.TestCase):
    def test_assert_demapping_method(self):
        with self.assertRaises(AssertionError):
            SymbolLogits2LLRs("asdfiu", 6)

    def test_output_dimensions1(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            d = SymbolLogits2LLRs("app", num_bits_per_symbol)
            batch_size = 99
            dim1 = 10
            dim2 = 12
            l = config.tf_rng.uniform([batch_size, dim1, dim2, 2**num_bits_per_symbol],
                                minval=-20.0, maxval=20.0, dtype=tf.dtypes.float32)
            llr = d(l)
            self.assertEqual(llr.shape, [batch_size, dim1, dim2, num_bits_per_symbol])

    def test_output_dimensions2(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            d = SymbolLogits2LLRs("app", num_bits_per_symbol)
            batch_size = 99
            l = config.tf_rng.uniform([batch_size, 2**num_bits_per_symbol],
                                minval=-20.0, maxval=20.0, dtype=tf.dtypes.float32)
            llr = d(l)
            self.assertEqual(llr.shape, [batch_size, num_bits_per_symbol])

    def test_llr_calc(self):
        "Test LLRs computation APP/MAXLOG"
        num_bits_per_symbol = 6
        num_points = 2**num_bits_per_symbol
        d_app = SymbolLogits2LLRs("app", num_bits_per_symbol)
        d_maxlog = SymbolLogits2LLRs("maxlog", num_bits_per_symbol)
        logits = config.tf_rng.uniform([100, 10, num_points],
                                        minval=-20.0, maxval=20.0, dtype=tf.dtypes.float32)
        llr_app = d_app(logits)
        llr_maxlog = d_maxlog(logits)
        for b in range(0, logits.shape[0]):
            for i in range(0, logits.shape[1]):
                llrnp_app = logsumexp(np.take(logits[b,i], d_app._c1),axis=0) - logsumexp(np.take(logits[b,i], d_app._c0),axis=0)
                llrtarget_app = llr_app[b,i].numpy()
                self.assertTrue(np.allclose(llrnp_app, llrtarget_app, atol=1e-5))

                llrnp_maxlog = np.max(np.take(logits[b,i], d_maxlog._c1),axis=0) - np.max(np.take(logits[b,i], d_maxlog._c0),axis=0)
                llrtarget_maxlog = llr_maxlog[b,i].numpy()
                self.assertTrue(np.allclose(llrnp_maxlog, llrtarget_maxlog, atol=1e-5))

    def test_graph_mode(self):
        num_bits_per_symbol = 4

        # simple precision

        l2l = SymbolLogits2LLRs("app", num_bits_per_symbol, precision="single")
        @tf.function
        def run(batch_size):
            logits = config.tf_rng.normal([batch_size, 150, 2**num_bits_per_symbol])
            return l2l(logits)
        self.assertEqual(run(100).shape, [100, 150, num_bits_per_symbol])
        self.assertEqual(run(400).shape, [400, 150, num_bits_per_symbol])

        # double precision

        l2l = SymbolLogits2LLRs("app", num_bits_per_symbol, precision="double")
        @tf.function
        def run(batch_size):
            logits = config.tf_rng.normal([batch_size, 150, 2**num_bits_per_symbol])
            return l2l(logits)
        self.assertEqual(run(100).shape, [100, 150, num_bits_per_symbol])
        self.assertEqual(run(400).shape, [400, 150, num_bits_per_symbol])

    def test_graph_mode_jit(self):
        num_bits_per_symbol = 4

        # simple precision

        l2l = SymbolLogits2LLRs("app", num_bits_per_symbol, precision="single")
        @tf.function(jit_compile=True)
        def run(batch_size):
            logits = config.tf_rng.normal([batch_size, 150, 2**num_bits_per_symbol])
            return l2l(logits)
        self.assertEqual(run(100).shape, [100, 150, num_bits_per_symbol])
        self.assertEqual(run(400).shape, [400, 150, num_bits_per_symbol])

        # double precision

        l2l = SymbolLogits2LLRs("app", num_bits_per_symbol, precision="double")
        @tf.function(jit_compile=True)
        def run(batch_size):
            logits = config.tf_rng.normal([batch_size, 150, 2**num_bits_per_symbol])
            return l2l(logits)
        self.assertEqual(run(100).shape, [100, 150, num_bits_per_symbol])
        self.assertEqual(run(400).shape, [400, 150, num_bits_per_symbol])

class TestLLRs2SymbolLogits(unittest.TestCase):

    def test_output_dimensions1(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            d = LLRs2SymbolLogits(num_bits_per_symbol)
            batch_size = 99
            dim1 = 10
            dim2 = 12
            l = config.tf_rng.uniform([batch_size, dim1, dim2, num_bits_per_symbol],
                                minval=-20.0, maxval=20.0, dtype=tf.dtypes.float32)
            llr = d(l)
            self.assertEqual(llr.shape, [batch_size, dim1, dim2, 2**num_bits_per_symbol])

    def test_output_dimensions2(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            d = LLRs2SymbolLogits(num_bits_per_symbol)
            batch_size = 99
            l = config.tf_rng.uniform([batch_size, num_bits_per_symbol],
                                minval=-20.0, maxval=20.0, dtype=tf.dtypes.float32)
            llr = d(l)
            self.assertEqual(llr.shape, [batch_size, 2**num_bits_per_symbol])

    def test_logits_calc(self):
        "Test logits computation"

        def sigmoid(x):
            return 1. / (1. + np.exp(-x))

        num_bits_per_symbol = 6
        num_points = 2**num_bits_per_symbol
        d = LLRs2SymbolLogits(num_bits_per_symbol)
        llrs = config.tf_rng.uniform([100, 10, num_bits_per_symbol],
                                        minval=-20.0, maxval=20.0, dtype=tf.dtypes.float32)
        logits = d(llrs)
        for b in range(0, llrs.shape[0]):
            for i in range(0, llrs.shape[1]):
                logits_ref = np.sum(np.log(sigmoid(d._a*llrs[b,i])), axis=1)
                self.assertTrue(np.allclose(logits[b,i].numpy(), logits_ref, atol=1e-5))

    def test_graph_mode(self):
        num_bits_per_symbol = 4

        # simple precision

        l2l = LLRs2SymbolLogits(num_bits_per_symbol, precision="single")
        @tf.function
        def run(batch_size):
            llrs = config.tf_rng.normal([batch_size, 150, num_bits_per_symbol])
            return l2l(llrs)
        self.assertEqual(run(100).shape, [100, 150, 2**num_bits_per_symbol])
        self.assertEqual(run(400).shape, [400, 150, 2**num_bits_per_symbol])

        # double precision

        l2l = LLRs2SymbolLogits(num_bits_per_symbol, precision="double")
        @tf.function
        def run(batch_size):
            llrs = config.tf_rng.normal([batch_size, 150, num_bits_per_symbol])
            return l2l(llrs)
        self.assertEqual(run(100).shape, [100, 150, 2**num_bits_per_symbol])
        self.assertEqual(run(400).shape, [400, 150, 2**num_bits_per_symbol])

    def test_graph_mode_jit(self):
        num_bits_per_symbol = 4

        # simple precision

        l2l = LLRs2SymbolLogits(num_bits_per_symbol, precision="single")
        @tf.function(jit_compile=True)
        def run(batch_size):
            llrs = config.tf_rng.normal([batch_size, 150, num_bits_per_symbol])
            return l2l(llrs)
        self.assertEqual(run(100).shape, [100, 150, 2**num_bits_per_symbol])
        self.assertEqual(run(400).shape, [400, 150, 2**num_bits_per_symbol])

        # double precision

        l2l = LLRs2SymbolLogits(num_bits_per_symbol, precision="double")
        @tf.function(jit_compile=True)
        def run(batch_size):
            llrs = config.tf_rng.normal([batch_size, 150, num_bits_per_symbol])
            return l2l(llrs)
        self.assertEqual(run(100).shape, [100, 150, 2**num_bits_per_symbol])
        self.assertEqual(run(400).shape, [400, 150, 2**num_bits_per_symbol])

class TestSymbolLogits2Moments(unittest.TestCase):
    def test_output_dimensions1(self):
        for num_bits_per_symbol in [2, 4, 6]:
            d = SymbolLogits2Moments("qam", num_bits_per_symbol)
            batch_size = 99
            dim1 = 10
            dim2 = 12
            l = config.tf_rng.uniform([batch_size, dim1, dim2, 2**num_bits_per_symbol],
                                minval=-20.0, maxval=20.0, dtype=tf.dtypes.float32)
            m, v = d(l)
            self.assertEqual(m.shape, [batch_size, dim1, dim2])
            self.assertEqual(v.shape, [batch_size, dim1, dim2])

    def test_output_dimensions2(self):
        for num_bits_per_symbol in [2, 4, 6]:
            d = SymbolLogits2Moments("qam", num_bits_per_symbol)
            batch_size = 99
            l = config.tf_rng.uniform([batch_size, 2**num_bits_per_symbol],
                                minval=-20.0, maxval=20.0, dtype=tf.dtypes.float32)
            m,v = d(l)
            self.assertEqual(m.shape, [batch_size])
            self.assertEqual(v.shape, [batch_size])

    def test_moments_calc(self):
        "Test LLRs computation APP/MAXLOG"
        num_bits_per_symbol = 6
        num_points = 2**num_bits_per_symbol
        c = Constellation("qam", num_bits_per_symbol)
        points = c.points

        d = SymbolLogits2Moments(constellation=c)
        logits = config.tf_rng.uniform([100, num_points],
                                        minval=-20.0, maxval=20.0, dtype=tf.dtypes.float32)
        m,v = d(logits)

        for l in range(0, logits.shape[0]):
            p = softmax(logits[l])
            m_ = np.sum(p*points)
            v_ = np.sum(p*np.square(np.abs(points-m_)))

            self.assertTrue(np.allclose(m[l], m_, atol=1e-5))
            self.assertTrue(np.allclose(v[l], v_, atol=1e-5))

    def test_graph_mode(self):
        num_bits_per_symbol = 4

        # simple precision

        l2m = SymbolLogits2Moments("qam", num_bits_per_symbol, precision="single")
        @tf.function
        def run(batch_size):
            logits = config.tf_rng.normal([batch_size, 150, 2**num_bits_per_symbol])
            return l2m(logits)

        m,v = run(100)
        self.assertEqual(m.shape, [100, 150])
        self.assertEqual(v.shape, [100, 150])

        m,v = run(400)
        self.assertEqual(m.shape, [400, 150])
        self.assertEqual(v.shape, [400, 150])

        # double precision

        l2m = SymbolLogits2Moments("qam", num_bits_per_symbol, precision="double")
        @tf.function
        def run(batch_size):
            logits = config.tf_rng.normal([batch_size, 150, 2**num_bits_per_symbol], dtype=tf.float64)
            return l2m(logits)

        m,v = run(100)
        self.assertEqual(m.shape, [100, 150])
        self.assertEqual(v.shape, [100, 150])

        m,v = run(400)
        self.assertEqual(m.shape, [400, 150])
        self.assertEqual(v.shape, [400, 150])

    def test_graph_mode_jit(self):
        num_bits_per_symbol = 4

        # simple precision

        l2m = SymbolLogits2Moments("qam", num_bits_per_symbol, precision="single")
        @tf.function(jit_compile=True)
        def run(batch_size):
            logits = config.tf_rng.normal([batch_size, 150, 2**num_bits_per_symbol])
            return l2m(logits)

        m,v = run(100)
        self.assertEqual(m.shape, [100, 150])
        self.assertEqual(v.shape, [100, 150])

        m,v = run(400)
        self.assertEqual(m.shape, [400, 150])
        self.assertEqual(v.shape, [400, 150])

        # double precision

        l2m = SymbolLogits2Moments("qam", num_bits_per_symbol, precision="double")
        @tf.function(jit_compile=True)
        def run(batch_size):
            logits = config.tf_rng.normal([batch_size, 150, 2**num_bits_per_symbol], dtype=tf.float64)
            return l2m(logits)

        m,v = run(100)
        self.assertEqual(m.shape, [100, 150])
        self.assertEqual(v.shape, [100, 150])

        m,v = run(400)
        self.assertEqual(m.shape, [400, 150])
        self.assertEqual(v.shape, [400, 150])
