/*
 * Copyright (c) 2025, sakumisu
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef EC_PORT_H
#define EC_PORT_H

#include "ec_netdev.h"

typedef void (*ec_htimer_cb)(void *arg);

ec_netdev_t *ec_netdev_low_level_init(uint8_t netdev_index);
void ec_netdev_low_level_poll_link_state(ec_netdev_t *netdev);
uint8_t *ec_netdev_low_level_get_txbuf(ec_netdev_t *netdev);
int ec_netdev_low_level_output(ec_netdev_t *netdev, uint32_t size);
int ec_netdev_low_level_input(ec_netdev_t *netdev);

void ec_htimer_start(uint32_t us, ec_htimer_cb cb, void *arg);
void ec_htimer_stop(void);
uint64_t ec_htimer_get_time_ns(void);
uint64_t ec_htimer_get_time_us(void);

#endif